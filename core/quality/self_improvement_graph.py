"""
LangGraph を使用した自己改善ループのステートフルワークフロー実装（拡張版）

機能:
- SQLite によるチェックポイント永続化
- Human-in-the-loop（重要な改善提案は人間承認を挟む）
- 複数子会社対応の基盤（HQ視点で複数ループを管理）
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, StateGraph

from core.models.organization import (
    Organization,
    OrganizationMetrics,
    QualityReview,
)
from core.quality.worker_executor import WorkerTaskExecutor
from core.state.manager import RepoStateManager

# ============================================================
# State Definition
# ============================================================

class SelfImprovementState(TypedDict):
    """自己改善ループの状態（メトリクスフィードバック対応）"""
    organization: Organization
    state_manager: RepoStateManager
    current_metrics: OrganizationMetrics | None
    pending_proposals: List[Dict[str, Any]]
    current_proposal: Dict[str, Any] | None
    latest_review: QualityReview | None
    improvement_history: List[Dict[str, Any]]
    cycle_count: int
    should_continue: bool
    messages: List[str]
    human_approval_required: bool
    human_approved: bool | None


# ============================================================
# Node Functions
# ============================================================

async def pickup_proposals(state: SelfImprovementState) -> Dict[str, Any]:
    proposals = state["state_manager"].get_pending_improvement_proposals(limit=20)
    metrics = state.get("current_metrics")

    msg = f"Picked up {len(proposals)} proposals"
    if metrics:
        msg += f" | 現在健康度: {metrics.health_score}"

    print(f"[Graph] {msg}")
    return {
        "pending_proposals": proposals,
        "messages": state.get("messages", []) + [msg],
        "human_approval_required": False,
        "human_approved": None,
    }


def prioritize_proposals(state: SelfImprovementState) -> Dict[str, Any]:
    proposals = sorted(
        state["pending_proposals"],
        key=lambda p: (p.get("priority") == "high", p.get("expected_impact", "")),
        reverse=True,
    )
    current = proposals[0] if proposals else None

    human_approval_required = False
    if current:
        if current.get("priority") == "high" or "large" in current.get("expected_impact", "").lower():
            human_approval_required = True
            print(f"[Graph] 重要提案のため Human-in-the-loop を有効化: {current.get('title')}")

    print(f"[Graph] 次に処理する提案: {current.get('title') if current else 'なし'}")

    return {
        "pending_proposals": proposals,
        "current_proposal": current,
        "human_approval_required": human_approval_required,
    }


async def wait_for_human_approval(state: SelfImprovementState) -> Dict[str, Any]:
    """
    Human-in-the-loop ノード
    このノードに到達するとグラフが中断する（interrupt_beforeで制御）。
    人間が承認/却下した結果を state に反映して再開する。
    """
    proposal = state["current_proposal"]
    print("\n[Human-in-the-Loop] 以下の改善提案について承認が必要です。")
    print(f"  タイトル      : {proposal.get('title')}")
    print(f"  説明          : {proposal.get('description')}")
    print(f"  期待効果      : {proposal.get('expected_impact')}")
    print(f"  優先度        : {proposal.get('priority')}")
    print(f"  実装難易度    : {proposal.get('implementation_difficulty')}")

    # ここでグラフが中断される（呼び出し側で interrupt_before を指定）
    # 再開時に human_approved が state に注入される想定
    approved = state.get("human_approved")

    if approved is None:
        # 初回到達時（中断前）
        print("[Human-in-the-Loop] グラフを中断します。人間の判断を待っています...")
        return {
            "messages": state.get("messages", []) + ["Waiting for human approval..."],
        }

    # 再開後
    decision = "承認" if approved else "却下"
    print(f"[Human-in-the-Loop] 人間の判断: {decision}")

    return {
        "human_approved": approved,
        "messages": state.get("messages", []) + [f"Human decision: {decision}"],
    }


async def execute_improvement(state: SelfImprovementState) -> Dict[str, Any]:
    proposal = state["current_proposal"]
    if not proposal:
        return {"should_continue": False}

    if state.get("human_approval_required") and not state.get("human_approved"):
        print("[Graph] 人間未承認のためこの改善をスキップします")
        return {
            "current_proposal": None,
            "messages": state.get("messages", []) + ["Skipped due to no human approval"],
        }

    title = proposal.get("title", "")
    file_path = proposal.get("file_path", "")

    if not file_path:
        print(f"[Graph] file_path なしのため実行不可（meta-level 提案）: {title}")
        state["state_manager"].update_proposal_status(str(proposal.get("id", "")), "rejected")
        return {
            "current_proposal": None,
            "messages": state.get("messages", []) + [f"Skipped (no file_path): {title}"],
            "cycle_count": state.get("cycle_count", 0) + 1,
        }

    print(f"[Graph] 改善を実行中: {title}")

    org = state["organization"]
    agents_list = org.get_all_agents()
    if not agents_list:
        print("[Graph] エージェントが見つかりません。スキップします。")
        return {"current_proposal": None}

    from agents.base import AgentTask
    from agents.improvement_executor_agent import ImprovementExecutorAgent

    executor_agent = ImprovementExecutorAgent(agents_list[0])

    task = AgentTask(
        task_type="improvement_execution",
        description=f"改善提案の適用: {title}",
        input={
            "repo_path": str(state["state_manager"].repo_path),
            "suggestion": proposal,
            # github_token は永続化ステートに含めない
        },
    )

    metrics = state.get("current_metrics")
    context = f"カテゴリ: {proposal.get('category')}"
    if metrics:
        context += f" | 現在健康度: {metrics.health_score} | 自律度: {metrics.autonomy_score}"

    executor = WorkerTaskExecutor(state["state_manager"], agents_list[0])

    async def improvement_task():
        result = await executor_agent.run(task)
        if result.success:
            state["state_manager"].update_proposal_status(str(proposal.get("id", "")), "done")
        else:
            state["state_manager"].update_proposal_status(str(proposal.get("id", "")), "failed")
        return result.output

    _, review, _ = await executor.execute_with_full_review(
        task_func=improvement_task,
        task_description=f"改善提案の実行: {title}",
        thinking_process=f"提案に基づく改善: {proposal.get('description', '')}",
        context=context,
    )

    history_entry = {
        "proposal": proposal,
        "review_score": review.overall_score,
    }

    return {
        "latest_review": review,
        "improvement_history": state.get("improvement_history", []) + [history_entry],
        "messages": state.get("messages", []) + [f"Executed: {title}"],
        "cycle_count": state.get("cycle_count", 0) + 1,
    }


def decide_next_step(state: SelfImprovementState) -> str:
    if not state.get("current_proposal"):
        print("[Graph] 処理する提案がなくなりました。")
        return END

    if state.get("cycle_count", 0) >= 5:
        print("[Graph] サイクル上限に達しました。")
        return END

    return "pickup_proposals"


# ============================================================
# Graph Construction（SQLite永続化 + Human-in-the-loop）
# ============================================================

def build_self_improvement_graph(
    checkpointer_path: str = "self_improvement_checkpoints.db"
) -> StateGraph:
    """
    SQLite永続化チェックポイント + Human-in-the-loop対応グラフ
    """
    workflow = StateGraph(SelfImprovementState)

    workflow.add_node("pickup_proposals", pickup_proposals)
    workflow.add_node("prioritize_proposals", prioritize_proposals)
    workflow.add_node("wait_for_human_approval", wait_for_human_approval)
    workflow.add_node("execute_improvement", execute_improvement)

    workflow.set_entry_point("pickup_proposals")
    workflow.add_edge("pickup_proposals", "prioritize_proposals")

    # Human-in-the-loop分岐
    workflow.add_conditional_edges(
        "prioritize_proposals",
        lambda state: "wait_for_human_approval" if state.get("human_approval_required") else "execute_improvement",
    )
    workflow.add_edge("wait_for_human_approval", "execute_improvement")

    workflow.add_conditional_edges(
        "execute_improvement",
        decide_next_step,
        {
            "pickup_proposals": "pickup_proposals",
            END: END,
        },
    )

    # SQLite による永続化チェックポイント
    conn = sqlite3.connect(checkpointer_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    graph = workflow.compile(checkpointer=checkpointer)
    setattr(graph, "_repocorp_checkpoint_conn", conn)

    return graph


# ============================================================
# 複数子会社対応（HQ視点）
# ============================================================

async def run_improvement_for_organization(
    organization: Organization,
    state_manager: RepoStateManager,
    current_metrics: OrganizationMetrics | None = None,
    thread_id: str | None = None,
    max_cycles: int = 3,
    enable_human_in_loop: bool = True,
):
    """
    単一Organizationに対して自己改善グラフを実行（メトリクスフィードバック対応）
    """
    graph = build_self_improvement_graph()

    initial_state: SelfImprovementState = {
        "organization": organization,
        "state_manager": state_manager,
        "current_metrics": current_metrics,
        "pending_proposals": [],
        "current_proposal": None,
        "latest_review": None,
        "improvement_history": [],
        "cycle_count": 0,
        "should_continue": True,
        "messages": [],
        "human_approval_required": False,
        "human_approved": None,
    }

    config = {"configurable": {"thread_id": thread_id or f"improvement_{organization.id}"}}

    print(f"\n=== {organization.name} の自己改善サイクル開始 ===\n")

    if enable_human_in_loop:
        final_state = await graph.ainvoke(
            initial_state,
            config=config,
            interrupt_before=["wait_for_human_approval"],
        )
    else:
        final_state = None
        async for event in graph.astream(initial_state, config=config):
            final_state = event

    print(f"\n=== {organization.name} の自己改善サイクル終了 ===\n")
    return final_state


async def run_group_improvement_cycles(
    organizations: List[Organization],
    state_managers: Dict[str, RepoStateManager],
    max_cycles_per_org: int = 2,
):
    """
    Core視点で複数Organizationの改善ループを順次実行する基盤
    将来的には並列実行や優先度付けも可能
    """
    print("=== グループ全体の自己改善サイクル開始 ===\n")

    results = {}
    for org in organizations:
        sm = state_managers.get(str(org.id))
        if not sm:
            print(f"StateManagerが見つかりません: {org.name}")
            continue

        result = await run_improvement_for_organization(
            org, sm, max_cycles=max_cycles_per_org
        )
        results[org.name] = result

    print("\n=== グループ全体の自己改善サイクル終了 ===\n")
    return results


# ============================================================
# Human-in-the-Loop ヘルパー関数（本格運用向け）
# ============================================================

async def request_human_approval_and_resume(
    graph,
    thread_id: str,
    approved: bool,
    config: dict | None = None,
) -> dict:
    """
    Human-in-the-Loopの本格運用用ヘルパー。

    1. グラフが "wait_for_human_approval" で中断している状態で呼ぶ
    2. 人間の判断（approved=True/False）を渡してグラフを再開
    """
    if config is None:
        config = {"configurable": {"thread_id": thread_id}}

    # human_approved を state に注入して再開
    result = await graph.ainvoke(
        {"human_approved": approved},
        config=config,
    )
    return result


def get_current_proposal_for_approval(graph, thread_id: str) -> dict | None:
    """
    中断中のグラフから、現在承認待ちの提案を取得するヘルパー
    （将来的にGUIで使う想定）
    """
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = graph.get_state(config)
        if state and state.values.get("current_proposal"):
            return state.values["current_proposal"]
    except Exception:
        pass
    return None
