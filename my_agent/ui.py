"""ターミナル表示と承認プロンプト。"""
from __future__ import annotations

import json
import sys


def printable(text: str) -> str:
    """制御文字を無害化する。

    LLMの出力にエスケープシーケンスが混ざると、承認画面の表示を
    書き換えて実際と違う内容に見せられてしまうため。
    """
    return "".join(c if c.isprintable() or c in "\n\t" else repr(c)[1:-1] for c in text)


class TerminalUI:
    def __init__(self, auto_approve: bool = False):
        self.auto_approve = auto_approve
        self.always: set[str] = set()  # このセッション中は確認を省くツール
        self.color = sys.stdout.isatty()

    def _style(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.color else text

    def on_text(self, text: str) -> None:
        print(printable(text), end="", flush=True)

    def on_tool_call(self, name: str, args: object) -> None:
        summary = printable(json.dumps(args, ensure_ascii=False))
        if len(summary) > 160:
            summary = summary[:160] + "…"
        print("\n" + self._style("36", f"● {name} {summary}"))

    def on_tool_result(self, result: str) -> None:
        lines = printable(result).splitlines()
        shown = "\n".join("  " + line[:160] for line in lines[:5])
        if len(lines) > 5:
            shown += f"\n  … 他 {len(lines) - 5} 行"
        print(self._style("2", shown))

    def approve(self, name: str, preview: str) -> bool:
        print(self._style("33", printable(preview)))
        if self.auto_approve or name in self.always:
            return True
        if not sys.stdin.isatty():
            print("(対話端末ではないため拒否しました。許可するには --yes を付けてください)")
            return False
        try:
            answer = input(f"実行しますか? [y]はい / [n]いいえ / [a]今後 {name} は常に許可: ")
        except EOFError:
            return False
        answer = answer.strip().lower()
        if answer == "a":
            self.always.add(name)
        return answer in ("y", "yes", "a")
