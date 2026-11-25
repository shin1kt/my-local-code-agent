"""文字列ユーティリティ。"""


def truncate(text, length):
    """length 文字を超える場合は末尾を "..." にして length 文字に収める。"""
    if len(text) <= length:
        return text
    return text[: length - 3] + "..."
