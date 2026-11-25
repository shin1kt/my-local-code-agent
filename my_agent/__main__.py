from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import readline  # noqa: F401  (input() で行編集と履歴を使えるようにする)
except ImportError:
    pass

from .agent import Agent
from .config import Config, normalize_host
from .llm import LLMError, OllamaClient
from .tools import ToolBox
from .ui import TerminalUI


def parse_args() -> tuple[Config, str | None]:
    p = argparse.ArgumentParser(prog="my_agent", description="ローカルLLMで動くコーディングエージェント")
    p.add_argument("prompt", nargs="?", help="依頼内容。省略すると対話モード")
    p.add_argument("-C", "--workspace", type=Path, default=Path.cwd(), help="作業対象のディレクトリ")
    p.add_argument("-m", "--model", help="Ollamaのモデル名")
    p.add_argument("--host", help="OllamaのURL")
    p.add_argument("--num-ctx", type=int, help="コンテキスト長(トークン)")
    p.add_argument("--max-steps", type=int, help="1回の依頼でLLMを呼び出す上限")
    p.add_argument("--yes", action="store_true", help="編集とコマンド実行を確認なしで許可する(危険)")
    a = p.parse_args()
    if not a.workspace.is_dir():
        p.error(f"ディレクトリがありません: {a.workspace}")

    config = Config.from_env(a.workspace)
    config.model = a.model or config.model
    config.host = normalize_host(a.host) if a.host else config.host
    config.num_ctx = a.num_ctx or config.num_ctx
    config.max_steps = a.max_steps or config.max_steps
    config.auto_approve = a.yes
    return config, a.prompt


def run_once(agent: Agent, prompt: str) -> bool:
    try:
        answer = agent.run(prompt)
        # 通常の回答はストリーミングで表示済み。上限到達のメッセージだけここで出す。
        print(f"\n{answer}" if agent.hit_limit else "")
        return not agent.hit_limit
    except LLMError as e:
        print(f"\nエラー: {e}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\n中断しました")
    return False


def main() -> int:
    config, prompt = parse_args()
    llm = OllamaClient(config.host, config.model, config.num_ctx, config.temperature)
    try:
        llm.check_model()
    except LLMError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1

    ui = TerminalUI(config.auto_approve)
    agent = Agent(llm, ToolBox(config.workspace), ui, config.num_ctx, config.max_steps)
    if prompt is not None:
        return 0 if run_once(agent, prompt) else 1

    print(f"モデル: {config.model} / ワークスペース: {config.workspace}")
    print("/clear で会話をリセット、/exit で終了、Ctrl-C で処理を中断")
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if line == "/exit":
            return 0
        if line == "/clear":
            agent.reset()
            print("会話をリセットしました")
        elif line:
            run_once(agent, line)


if __name__ == "__main__":
    sys.exit(main())
