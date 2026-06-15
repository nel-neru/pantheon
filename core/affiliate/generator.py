"""短尺動画台本の生成 — スケジュール設計・プロンプト構築・claude 生成・決定的フォールバック。

``claude_available()`` で実生成を遅延ゲートし、未導入/失敗時は決定論テンプレに倒す
（content_runner と同じ思想＝import や dry-run・テストを壊さない）。半年分の量産は Workflow が
バッチごとに改善しながら行い、結果を ``ShortVideoCalendarStore`` に投入する。
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List, Optional

from core.affiliate.programs import AffiliateProgram
from core.affiliate.short_video import (
    HOOK_TYPES,
    PLATFORM_YOUTUBE_SHORTS,
    ShortVideoPost,
    schedule_dates,
)

# 誇大表現・PR 明記の制約（景表法/規約対策）。プロンプトと fallback の両方で守る。
COMPLIANCE_NOTE = (
    "誇大・断定的な収益/効果の保証表現は禁止。広告であることがわかる表現（PR）を含める。"
    "医療・投資・健康などの YMYL 断定は避ける。"
)


def plan_schedule(
    programs: List[AffiliateProgram],
    start: date,
    count: int,
) -> List[Dict[str, Any]]:
    """``count`` 日分の (day_index, date, program, hook_type) 割当を返す。

    - has_affiliate=True を優先しつつ、集客ネタ(tier c)も一定混ぜて再生数を取りにいく。
    - フック型は 6 種をローテーション（連日の被りを避ける）。
    - program はラウンドロビンで均等に露出。
    """
    if count <= 0:
        return []
    affiliate = [p for p in programs if p.has_affiliate]
    bait = [p for p in programs if not p.has_affiliate]
    # 4:1 で affiliate を主、集客ネタを従に混ぜる（affiliate が無ければ全部 bait）。
    rotation: List[AffiliateProgram] = []
    ai = bi = 0
    if affiliate or bait:
        for i in range(max(len(affiliate), 1) * 5):
            if affiliate and i % 5 != 4:
                rotation.append(affiliate[ai % len(affiliate)])
                ai += 1
            elif bait:
                rotation.append(bait[bi % len(bait)])
                bi += 1
            elif affiliate:
                rotation.append(affiliate[ai % len(affiliate)])
                ai += 1
    if not rotation:
        rotation = affiliate or bait

    dates = schedule_dates(start, count)
    plan: List[Dict[str, Any]] = []
    for i, day in enumerate(dates):
        program = rotation[i % len(rotation)] if rotation else None
        hook = HOOK_TYPES[i % len(HOOK_TYPES)]
        plan.append(
            {
                "day_index": i + 1,
                "date": day,
                "program": program,
                "hook_type": hook,
            }
        )
    return plan


def build_prompt(
    program: AffiliateProgram,
    hook_type: str,
    date_str: str,
    day_index: int,
    learnings: str = "",
) -> Dict[str, str]:
    """claude/Workflow エージェント向けの (system, user) プロンプトを構築する。"""
    topics = "、".join(program.topics) if program.topics else program.category
    system = (
        "あなたは日本語 YouTube Shorts のアフィリエイト動画の構成作家です。"
        "視聴維持率と概要欄クリックを最大化する、45秒以内・1ツール1ベネフィットの台本を作ります。"
        f"\n制約: {COMPLIANCE_NOTE}"
        "\n必ず JSON だけを出力する（前後に文章を付けない）。キーは "
        "title, hook, script, onscreen_text(配列), caption, hashtags(配列), cta。"
    )
    monetize = (
        "この回は概要欄のアフィリエイトリンクへ誘導する（CTAで『概要欄から無料で試せる』と伝える）。"
        if program.has_affiliate
        else "この回はアフィリエイト無し。再生数を取り、概要欄では関連の有料ツールへ自然に送客する。"
    )
    hook_guide = {
        "pain": "冒頭で視聴者の『あるある悩み』を断定的に提示して掴む。",
        "result": "冒頭で具体的な成果・数字（時短/工数削減）を提示する。",
        "vs": "他ツールや手作業との比較で優位を見せる。",
        "howto": "『3ステップで〜』のように手順を見せる。",
        "mistake": "『これやってる人ヤバい』系のやりがち失敗から入る。",
        "tier": "『○○Top3/ランキング』形式で複数を見せ、本命に誘導する。",
    }.get(hook_type, "悩み提示から入る。")
    user = (
        f"対象ツール: {program.name}（カテゴリ: {program.category}）\n"
        f"切り口テーマ候補: {topics}\n"
        f"フック型: {hook_type} — {hook_guide}\n"
        f"投稿日: {date_str}（Day {day_index}）\n"
        f"{monetize}\n"
    )
    if learnings:
        user += f"\n直近バッチの学び（反映せよ）: {learnings}\n"
    user += (
        "\n出力 JSON 例の形式に厳密に従うこと。script は 5〜8 行の撮影用ビート（口語）。"
        "hashtags は #付き 5〜8 個（日本語中心、AIツール/Shorts 系）。"
    )
    return {"system": system, "user": user}


def _hashtags_for(program: AffiliateProgram) -> List[str]:
    base = ["#AIツール", "#shorts", "#業務効率化", "#AI活用"]
    cat = {
        "video": ["#動画編集", "#動画制作"],
        "voice": ["#AI音声", "#ナレーション"],
        "writing": ["#AIライティング", "#ブログ"],
        "design": ["#デザイン", "#サムネ"],
        "automation": ["#仕事効率化", "#自動化"],
        "research": ["#リサーチ", "#情報収集"],
        "general": ["#chatgpt", "#生成AI"],
    }.get(program.category, [])
    name_tag = "#" + "".join(ch for ch in program.name if ch.isalnum())
    return base + cat + [name_tag]


def fallback_post(
    program: AffiliateProgram,
    hook_type: str,
    date_str: str,
    day_index: int,
) -> ShortVideoPost:
    """claude 不在/失敗時の決定論テンプレ。offline でも使える品質を担保する。"""
    name = program.name
    topic = program.topics[0] if program.topics else program.category
    hooks = {
        "pain": f"{topic}、まだ手作業でやってませんか？それ、{name}で一瞬です。",
        "result": f"{name}を使ったら{topic}が10分→1分になった話、します。",
        "vs": f"{topic}、手作業と{name}でどれだけ違うか比べてみた。",
        "howto": f"{name}で{topic}を終わらせる3ステップ、見せます。",
        "mistake": f"{topic}でこれやってる人、時間めっちゃ損してます（{name}で解決）。",
        "tier": f"{program.category}系AIツールTop3、本命は{name}でした。",
    }
    hook = hooks.get(hook_type, hooks["pain"])
    cta = (
        f"概要欄に{name}を無料で試せるリンク置いときます（PR）。"
        if program.has_affiliate
        else "概要欄に関連の便利ツールまとめておきます（PR）。"
    )
    script = "\n".join(
        [
            f"1) フック: {hook}",
            f"2) 課題: {topic}を手作業でやると時間も品質もブレる。",
            f"3) 解決: {name}ならこの操作だけ（画面で手元を見せる）。",
            "4) Before→After: 実際の所要時間/仕上がりの差を数字で。",
            f"5) 一言: {name}の強みは「{(program.commission and '継続報酬') or program.category}」より使い心地。",
            f"6) CTA: {cta}",
        ]
    )
    title = f"【{name}】{topic}が一瞬で終わるAI活用 #shorts"
    caption = f"{topic}を時短する{name}の使い方。無料で試せます（PR）。"
    return ShortVideoPost(
        day_index=day_index,
        date=date_str,
        platform=PLATFORM_YOUTUBE_SHORTS,
        program_name=name,
        program_id=program.program_id,
        hook_type=hook_type,
        title=title,
        hook=hook,
        script=script,
        onscreen_text=[topic, name, "Before→After", "無料で試せる(PR)"],
        caption=caption,
        hashtags=_hashtags_for(program),
        cta=cta,
        affiliate_url_slug=f"{program.program_id.replace('aff:', '')}-d{day_index:03d}",
        notes="fallback",
    )


def post_from_llm_json(
    raw: Dict[str, Any],
    program: AffiliateProgram,
    hook_type: str,
    date_str: str,
    day_index: int,
) -> ShortVideoPost:
    """LLM の JSON 出力から ShortVideoPost を組み立てる（欠損は fallback 値で補完）。"""
    fb = fallback_post(program, hook_type, date_str, day_index)

    def _s(key: str, default: str) -> str:
        v = raw.get(key)
        return str(v).strip() if isinstance(v, (str, int, float)) and str(v).strip() else default

    def _list(key: str, default: List[str]) -> List[str]:
        v = raw.get(key)
        if isinstance(v, list):
            out = [str(x).strip() for x in v if isinstance(x, (str, int, float)) and str(x).strip()]
            return out or default
        return default

    return ShortVideoPost(
        day_index=day_index,
        date=date_str,
        platform=PLATFORM_YOUTUBE_SHORTS,
        program_name=program.name,
        program_id=program.program_id,
        hook_type=hook_type,
        title=_s("title", fb.title),
        hook=_s("hook", fb.hook),
        script=_s("script", fb.script),
        onscreen_text=_list("onscreen_text", fb.onscreen_text),
        caption=_s("caption", fb.caption),
        hashtags=_list("hashtags", fb.hashtags),
        cta=_s("cta", fb.cta),
        affiliate_url_slug=fb.affiliate_url_slug,
    )


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """LLM 応答から最初の JSON オブジェクトを取り出す（前後に文があっても拾う）。"""
    import re

    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)  # greedy: ネスト全体を捕捉
    if not m:
        return None
    try:
        obj = json.loads(m.group())
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


async def generate_post(
    program: AffiliateProgram,
    hook_type: str,
    date_str: str,
    day_index: int,
    *,
    learnings: str = "",
    downgrade: bool = False,
) -> ShortVideoPost:
    """1 本生成する。claude 利用可なら実生成、失敗/不在は決定論テンプレ。"""
    from core.runtime.claude_code import claude_available

    if not claude_available():
        return fallback_post(program, hook_type, date_str, day_index)
    try:
        from core.llm import LLMMessage, get_llm_provider

        prompt = build_prompt(program, hook_type, date_str, day_index, learnings)
        provider = get_llm_provider()
        response = await provider.generate(
            messages=[
                LLMMessage(role="system", content=prompt["system"]),
                LLMMessage(role="user", content=prompt["user"]),
            ],
            temperature=0.7,
            max_tokens=1200,
            task_type="content_generation",
            downgrade=downgrade,
        )
        raw = _extract_json(getattr(response, "content", "") or "")
        if raw:
            return post_from_llm_json(raw, program, hook_type, date_str, day_index)
    except Exception:  # noqa: BLE001 — 生成失敗はテンプレに倒す（量産を止めない）
        pass
    return fallback_post(program, hook_type, date_str, day_index)
