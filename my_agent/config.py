"""設定。優先順位は CLI 引数 > 環境変数 > デフォルト値。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "qwen2.5:14b"
DEFAULT_HOST = "http://localhost:11434"
DEFAULT_NUM_CTX = 32768


def normalize_host(host: str) -> str:
    """OLLAMA_HOST は "127.0.0.1:11434" のようにスキームなしで書かれることがある。"""
    if "://" in host:
        return host.rstrip("/")
    host = host.rstrip("/")
    return f"http://{host}" if ":" in host else f"http://{host}:11434"


@dataclass
class Config:
    workspace: Path
    model: str = DEFAULT_MODEL
    host: str = DEFAULT_HOST
    num_ctx: int = DEFAULT_NUM_CTX
    temperature: float = 0.1
    max_steps: int = 25  # 1回の依頼でLLMを呼び出す上限
    auto_approve: bool = False

    @classmethod
    def from_env(cls, workspace: Path) -> "Config":
        return cls(
            workspace=workspace.resolve(),
            model=os.environ.get("MY_AGENT_MODEL", DEFAULT_MODEL),
            host=normalize_host(os.environ.get("OLLAMA_HOST") or DEFAULT_HOST),
            num_ctx=int(os.environ.get("MY_AGENT_NUM_CTX", DEFAULT_NUM_CTX)),
        )
