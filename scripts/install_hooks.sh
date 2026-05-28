#!/bin/bash
# git hooks をインストールするスクリプト
set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"
SOURCE_DIR="$REPO_ROOT/scripts/hooks"

echo "Git hooks をインストールしています..."

mkdir -p "$HOOKS_DIR"
mkdir -p "$SOURCE_DIR"

cp "$SOURCE_DIR/pre-commit" "$HOOKS_DIR/pre-commit"
chmod +x "$HOOKS_DIR/pre-commit"

echo "インストール完了: pre-commit フック"
