# RepoCorp AI — 開発タスクランナー
# 使い方: make <target>。`make verify` で CI 同等のチェックを一括実行。

.PHONY: help install test cov lint fix serve build fe-test fe-install verify audit

help:
	@echo "install   - Python(-e .[dev,web]+ruff) と frontend 依存をインストール"
	@echo "test      - pytest (バックエンド)"
	@echo "cov       - pytest + カバレッジゲート (--cov-fail-under=70, F7)"
	@echo "lint      - ruff check ."
	@echo "fix       - ruff check --fix ."
	@echo "build     - frontend を build (tsc + vite)"
	@echo "fe-test   - vitest (フロントエンド)"
	@echo "serve     - Web GUI を起動 (localhost)"
	@echo "verify    - lint + test + build + fe-test を一括実行 (CI 同等)"
	@echo "audit     - 依存脆弱性スキャン (pip-audit / npm audit)"

install:
	python -m pip install -e ".[dev,web]" ruff
	npm --prefix web/frontend ci

fe-install:
	npm --prefix web/frontend ci

test:
	python -m pytest tests/ -q --tb=short

cov:
	python -m pytest tests/ -q --tb=short --cov --cov-report=term-missing --cov-fail-under=70

lint:
	ruff check .

fix:
	ruff check --fix .

build:
	npm --prefix web/frontend run build

fe-test:
	npm --prefix web/frontend run test

serve:
	python main.py serve

verify: lint test build fe-test
	@echo "✅ all checks passed"

audit:
	-pip-audit
	-npm --prefix web/frontend audit
