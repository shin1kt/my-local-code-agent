"""Ollama のネイティブAPI (/api/chat) クライアント。

OpenAI互換API (/v1) ではなくネイティブAPIを使うのは、リクエストごとに
num_ctx (コンテキスト長) を指定するため。指定しないとサーバ既定値が使われ、
短い場合は会話の先頭が警告なしに切り捨てられる。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Callable

Message = dict[str, Any]


class LLMError(Exception):
    pass


class OllamaClient:
    def __init__(self, host: str, model: str, num_ctx: int, temperature: float, timeout: float = 600):
        self.host = host
        self.model = model
        self.options = {"num_ctx": num_ctx, "temperature": temperature}
        self.timeout = timeout
        self.stats = {"calls": 0, "prompt_tokens": 0, "output_tokens": 0, "output_seconds": 0.0}
        # localhost 宛ての通信が環境変数の HTTP_PROXY に流れないようにする
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _open(self, path: str, payload: dict | None = None, timeout: float | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.host + path, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            return self._opener.open(req, timeout=timeout or self.timeout)
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            raise LLMError(f"Ollama がエラーを返しました ({e.code}): {body}") from e
        except OSError as e:  # URLError, タイムアウト等
            raise LLMError(
                f"Ollama ({self.host}) に接続できません: {e}\n`ollama serve` で起動してください。"
            ) from e

    def check_model(self) -> None:
        """モデルの有無とツール呼び出しへの対応を起動時に確認する。"""
        try:
            with self._open("/api/show", {"model": self.model}, timeout=10) as res:
                info = json.load(res)
        except LLMError as e:
            if "(404)" in str(e):
                raise LLMError(
                    f"モデル {self.model} がありません。`ollama pull {self.model}` を実行してください。"
                ) from e
            raise
        caps = info.get("capabilities")
        if caps is not None and "tools" not in caps:
            raise LLMError(f"モデル {self.model} はツール呼び出しに対応していません (capabilities: {caps})")

    def load(self) -> None:
        """モデルをメモリに読み込む(大きいモデルは数分かかる)。"""
        payload = {"model": self.model, "options": self.options, "stream": False}
        with self._open("/api/generate", payload, timeout=1800) as res:
            res.read()

    def unload(self) -> None:
        payload = {"model": self.model, "keep_alive": 0, "stream": False}
        with self._open("/api/generate", payload, timeout=60) as res:
            res.read()

    def gpu_percent(self) -> int | None:
        """モデルのうちGPUメモリに載っている割合。100未満だと大幅に遅くなる。"""
        with self._open("/api/ps", timeout=10) as res:
            for m in json.load(res).get("models", []):
                if self.model in (m.get("name"), m.get("model"), m.get("name", "").removesuffix(":latest")):
                    return round(100 * m.get("size_vram", 0) / m["size"]) if m.get("size") else None
        return None

    def chat(
        self, messages: list[Message], tools: list[dict], on_text: Callable[[str], None]
    ) -> Message:
        """ストリーミングで1回応答させ、組み立てた assistant メッセージを返す。"""
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "stream": True,
            "options": self.options,
        }
        content: list[str] = []
        thinking: list[str] = []
        tool_calls: list[dict] = []
        finished = False
        try:
            with self._open("/api/chat", payload) as res:
                for line in res:  # 1行1JSON (NDJSON)
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise LLMError(chunk["error"])
                    msg = chunk.get("message", {})
                    if msg.get("content"):
                        content.append(msg["content"])
                        on_text(msg["content"])
                    if msg.get("thinking"):
                        thinking.append(msg["thinking"])
                    tool_calls.extend(msg.get("tool_calls") or [])
                    if chunk.get("done"):
                        finished = True
                        self.stats["calls"] += 1
                        self.stats["prompt_tokens"] += chunk.get("prompt_eval_count", 0)
                        self.stats["output_tokens"] += chunk.get("eval_count", 0)
                        self.stats["output_seconds"] += chunk.get("eval_duration", 0) / 1e9
        except (OSError, ValueError) as e:
            raise LLMError(f"応答の受信に失敗しました: {e}") from e
        if not finished:
            raise LLMError("応答が途中で切れました")

        message: Message = {"role": "assistant", "content": "".join(content)}
        if thinking:
            message["thinking"] = "".join(thinking)
        if not tool_calls:
            names = {t["function"]["name"] for t in tools}
            tool_calls = parse_text_tool_calls(message["content"], names)
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message


def parse_text_tool_calls(text: str, known_tools: set[str]) -> list[dict]:
    """本文にJSONとして書かれたツール呼び出しを救済する。

    qwen2.5-coder などは tool_calls ではなく本文にJSONを書くことがある。
    説明文中のJSON例を誤って実行しないよう、<tool_call> タグで囲まれているか、
    本文全体がJSON(コードブロック可)の場合だけを対象にする。
    """
    candidates = re.findall(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL)
    if not candidates:
        body = text.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n?```", body, re.DOTALL)
        candidates = [fenced.group(1) if fenced else body]

    calls = []
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        for item in data if isinstance(data, list) else [data]:
            if not isinstance(item, dict):
                continue
            name, args = item.get("name"), item.get("arguments")
            if isinstance(name, str) and name in known_tools and isinstance(args, dict):
                calls.append({"function": {"name": name, "arguments": args}})
    return calls
