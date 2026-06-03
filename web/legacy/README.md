# web/legacy — アーカイブ（配信されません）

ここは **旧 WebGUI（単一HTMLファイル版）のアーカイブ**です。サーバーからは配信されません。

- `index.html` — marked.js を CDN 読み込みする旧来のバニラ JS 製 UI。
  React 版（`web/frontend/` → ビルド成果物 `web/dist/`）が唯一の正典 UI になったため退避しました。

## 正典 UI

- ソース: `web/frontend/`（React + Vite + TypeScript）
- ビルド: `npm --prefix web/frontend install && npm --prefix web/frontend run build` → `web/dist/`
- 配信: `web/server.py` が `web/dist/` を配信（未ビルド時は案内ページを返す）

このディレクトリのファイルは参照用に残しているだけで、編集・保守の対象外です。
