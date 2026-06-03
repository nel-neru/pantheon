"""
ErrorMessageHelper — ユーザーフレンドリーエラーメッセージ (I-10)
"""

from __future__ import annotations

ERROR_MESSAGES: dict[str, dict] = {
    "MISSING_API_KEY": {
        "message": "ANTHROPIC_API_KEY が未設定です。",
        "help": ".env ファイルに ANTHROPIC_API_KEY=sk-... を追加してください。",
        "docs": "https://console.anthropic.com/ でAPIキーを取得できます。",
    },
    "ORG_NOT_FOUND": {
        "message": "組織が見つかりません。",
        "help": "repocorp org add <name> で組織を作成してください。",
    },
    "REPO_NOT_FOUND": {
        "message": "リポジトリが見つかりません。",
        "help": "repocorp org add コマンドでリポジトリパスを正しく指定してください。",
    },
    "DB_CORRUPTED": {
        "message": "データベースに問題があります。",
        "help": "repocorp doctor コマンドで診断・修復を試みてください。",
    },
}


class ErrorMessageHelper:
    """Format friendly error messages from codes and exceptions."""

    def format_error(self, error_code: str, extra_context: str = "") -> str:
        payload = ERROR_MESSAGES.get(
            error_code,
            {
                "message": "予期しないエラーが発生しました。",
                "help": "詳細ログを確認して再実行してください。",
            },
        )
        lines = [f"[ERROR] {payload['message']}", f"💡 {payload['help']}"]
        if payload.get("docs"):
            lines.append(str(payload["docs"]))
        if extra_context:
            lines.append(extra_context)
        return "\n".join(lines)

    def wrap_exception(self, e: Exception) -> str:
        if isinstance(e, KeyError):
            return self.format_error("ORG_NOT_FOUND", extra_context=str(e))
        if isinstance(e, FileNotFoundError):
            return self.format_error("REPO_NOT_FOUND", extra_context=str(e))
        if type(e).__name__ in {"sqlite3.DatabaseError", "DatabaseError"}:
            return self.format_error("DB_CORRUPTED", extra_context=str(e))
        if isinstance(e, PermissionError):
            return self.format_error("REPO_NOT_FOUND", extra_context=str(e))
        return self.format_error("UNKNOWN", extra_context=f"{type(e).__name__}: {e}")
