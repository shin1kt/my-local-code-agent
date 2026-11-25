"""会話履歴をコンテキスト長に収める。"""
from __future__ import annotations

import json

from .llm import Message

ELIDED = "[古いツール結果のため省略。必要ならもう一度ツールを実行すること]"
KEEP_RECENT_TOOL_RESULTS = 4

# 失敗したまま終わろうとしたLLMに続行を促す。role は user だがユーザーの依頼ではない。
NUDGE = """\
(自動メッセージ) 最後に実行したツールまたはコマンドは失敗したままです。まだ試せる方法があれば、説明だけで終わらず、ツールを呼び出して作業を続けてください。
本当に続行できない場合だけ、理由を報告してください。"""


def estimate_tokens(messages: list[Message]) -> int:
    """おおまかなトークン数。ASCIIは4文字、日本語などは1文字で1トークンとみなす。"""
    text = json.dumps(messages, ensure_ascii=False)
    ascii_count = sum(c.isascii() for c in text)
    return ascii_count // 4 + (len(text) - ascii_count)


def compact(messages: list[Message], budget: int) -> list[Message]:
    """budget に収まるよう縮める。(1) 古いツール結果を省略 → (2) 古い依頼ごと削除。

    先頭の system と、現在の依頼(NUDGE を除く最後の user)以降は必ず残す。
    """
    if estimate_tokens(messages) <= budget:
        return messages
    result = list(messages)

    tool_indexes = [i for i, m in enumerate(result) if m["role"] == "tool"]
    for i in tool_indexes[:-KEEP_RECENT_TOOL_RESULTS]:
        result[i] = {**result[i], "content": ELIDED}
        if estimate_tokens(result) <= budget:
            return result

    while estimate_tokens(result) > budget:
        users = [i for i, m in enumerate(result) if m["role"] == "user" and m["content"] != NUDGE]
        if len(users) < 2:
            break
        result = result[:1] + result[users[1]:]
    return result
