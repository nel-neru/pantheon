# Skills Manifest

Pantheon で利用できるスキル一覧です。

| Skill ID | Description | Compatible agent types | Recommended combinations |
| --- | --- | --- | --- |
| `agent_workflow_design` | LangGraph/エージェントワークフロー・Human-in-the-Loop設計 | `chat_agent`, `orchestrator`, `tool_designer`, `workflow_designer` | `strategic_planning`, `tool_integration` |
| `codebase_exploration` | コードベース調査・依存関係分析・アーキテクチャ把握 | `code_reviewer`, `codebase_explorer`, `self_code_writer` | `deep_research`, `performance_analysis`, `prompt_engineering` |
| `corporate_research` | 業界トレンド・競合分析・技術動向リサーチ | `corporate_researcher` | `deep_research` |
| `deep_research` | 技術調査・根本原因分析・詳細調査 | `codebase_explorer`, `corporate_researcher`, `knowledge_curator`, `performance_analyst`, `security_auditor` | `codebase_exploration`, `corporate_research`, `knowledge_curation`, `performance_analysis`, `tool_integration` |
| `knowledge_curation` | 知識管理・ベストプラクティス抽出・ドキュメント整備 | `knowledge_curator`, `prompt_optimizer` | `deep_research`, `prompt_engineering` |
| `org_design` | AI組織構造設計・責任分離・スケーリング設計 | `org_designer`, `strategic_planner` | `strategic_planning` |
| `performance_analysis` | パフォーマンス計測・ボトルネック分析・最適化提案 | `code_reviewer`, `performance_analyst` | `codebase_exploration`, `deep_research` |
| `prompt_engineering` | LLMプロンプト最適化・トークン効率・出力品質改善 | `improvement_executor`, `prompt_optimizer`, `self_code_writer` | `codebase_exploration`, `knowledge_curation`, `tool_integration` |
| `quality_guardian` | コード変更に伴う品質保証を自律的に実行するスキル | `quality_guardian` | `code_review` |
| `strategic_planning` | 長期戦略・ロードマップ・システム方向性の立案 | `chat_agent`, `orchestrator`, `org_designer`, `strategic_planner`, `workflow_designer` | `agent_workflow_design`, `org_design` |
| `tool_integration` | 外部API・ツール統合・セキュリティレビュー | `improvement_executor`, `security_auditor`, `tool_designer` | `agent_workflow_design`, `deep_research`, `prompt_engineering` |
