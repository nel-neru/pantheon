---
name: "source-command-spawn-org"
description: "ジャンル/ペルソナ/デザインを指定して外部 Organization を1コマンド量産する"
---

# source-command-spawn-org

Use this skill when the user asks to run the migrated source command `spawn-org`.

## Command Template

# /spawn-org — ジャンル別エキスパート組織を量産する

業界ジャンルから組織構成を LLM が設計し、ペルソナ・デザインスタイルを付けて外部
Organization を1コマンドで作る（リポジトリ肥大化を避けるため既定 `isolation=external`）。

```powershell
.\.venv\Scripts\python.exe main.py org create `
  --name "GameDevStudio" `
  --genre game_dev `
  --persona sns_growth_hacker `
  --design pixel
```

引数:

- `--genre` (必須) — `ai` / `side_business` / `video_edit` / `game_dev` / `business` など。
  LLM が `config/departments/generated/<genre>.yaml` に Division/Team/skill 構成を設計・検証・保存
  （Codex 不在時は決定論フォールバック）。
- `--persona` — `config/personas/<id>`（投稿/コンテンツの口調。例 `sns_growth_hacker`,
  `luxury_brand_voice`）。一覧は `GET /api/personas`。
- `--design` — `config/design_styles/<id>`（`minimal/luxury/art/3d/pixel/vibrant`）。
  一覧は `GET /api/design-styles`。
- `--repo` — 省略時は `workspaces_root` 配下に自動作成＋`git init`。
- `--isolation-level` — 既定 `external`（本体を汚さない）。

作成後: `pantheon analyze --org-name "<name>"` で分析→改善提案を回し始める。
