"""1件の評価を実行して採点する。

採点はエージェントが作業したディレクトリではなく、別のディレクトリに成果物を
コピーし、保護対象ファイルを元に戻し、非公開テストを加えてから行う。
テストを書き換えて通した場合は、採点結果にかかわらず不合格にする。
"""
from __future__ import annotations

import difflib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from my_agent.agent import Agent
from my_agent.llm import LLMError, OllamaClient
from my_agent.tools import ToolBox

TASKS_DIR = Path(__file__).parent / "tasks"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")
CHECK_TIMEOUT = 60

# 評価中に承認なしで実行してよいコマンド。シェルの連結や置換を含むものは許可しない。
SHELL_META = re.compile(r"[;&|<>`$\n\r(){}\\*?~]")
SAFE_COMMAND = re.compile(
    r"(python3?\s+-m\s+(unittest|pytest|py_compile)(\s.*)?"
    r"|python3?\s+[\w][\w./-]*\.py(\s.*)?"
    r"|pytest(\s.*)?"
    r"|(ls|cat|head|tail|grep|wc|pwd)(\s.*)?)"
)


def is_safe_command(command: str) -> bool:
    command = command.strip().removesuffix("2>&1").strip()
    if SHELL_META.search(command) or not SAFE_COMMAND.fullmatch(command):
        return False
    # ワークスペース外のパスは参照させない
    return not any(
        part.startswith("/") or "=/" in part or ".." in part.split("/")
        for part in re.split(r"[\s'\"]+", command)
    )


class Deadline(BaseException):
    """制限時間切れ。ツール内の except OSError などで握りつぶされないよう BaseException にする。"""


@contextmanager
def time_limit(seconds: int):
    def on_alarm(signum, frame):
        raise Deadline

    previous = signal.signal(signal.SIGALRM, on_alarm)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


class EvalUI:
    """自動で承認し、すべてをログに残すUI。"""

    def __init__(self, log, allow_all_commands: bool):
        self.log = log
        self.allow_all_commands = allow_all_commands
        self.tool_calls = self.tool_errors = self.denied = 0

    def on_text(self, text: str) -> None:
        self.log.write(text)
        self.log.flush()

    def on_tool_call(self, name: str, args: object) -> None:
        self.tool_calls += 1
        self.log.write(f"\n● {name} {json.dumps(args, ensure_ascii=False)}\n")

    def on_tool_result(self, result: str) -> None:
        self.tool_errors += result.startswith("ERROR")
        self.log.write(result + "\n")
        self.log.flush()

    def approve(self, name: str, preview: str) -> bool:
        if name != "run_command" or self.allow_all_commands:
            return True
        ok = is_safe_command(preview.removeprefix("$ "))
        self.denied += not ok
        return ok


@dataclass
class Task:
    name: str
    title: str
    prompt: str
    protected: list[str]
    checks: list[str]

    @property
    def workspace(self) -> Path:
        return TASKS_DIR / self.name / "workspace"

    @property
    def hidden(self) -> Path:
        return TASKS_DIR / self.name / "hidden"


def load_tasks(names: list[str] | None = None) -> list[Task]:
    available = sorted(p.parent.name for p in TASKS_DIR.glob("*/task.json"))
    unknown = set(names or []) - set(available)
    if unknown:
        raise ValueError(f"不明な課題: {', '.join(sorted(unknown))}(使える課題: {', '.join(available)})")
    return [
        Task(name=n, **json.loads((TASKS_DIR / n / "task.json").read_text(encoding="utf-8")))
        for n in available
        if not names or n in names
    ]


def modified_files(task: Task, workspace: Path) -> list[str]:
    """変更または削除された保護対象ファイル。"""
    return [
        f
        for f in task.protected
        if not (workspace / f).is_file() or (workspace / f).read_bytes() != (task.workspace / f).read_bytes()
    ]


def grade(task: Task, workspace: Path) -> tuple[bool, str]:
    """(合格か, 不合格の理由)。"""
    tampered = modified_files(task, workspace)
    if tampered:
        return False, f"保護対象を変更: {', '.join(tampered)}"
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "check"
        shutil.copytree(workspace, target, ignore=IGNORE, symlinks=True)
        shutil.copytree(task.hidden, target, dirs_exist_ok=True, ignore=IGNORE)
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", *task.checks],
                cwd=target, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                errors="replace", timeout=CHECK_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return False, "採点テストがタイムアウト"
    ran = re.search(r"^Ran (\d+) test", proc.stderr, re.MULTILINE)
    if proc.returncode == 0 and ran and int(ran.group(1)) > 0:
        return True, ""
    last = (proc.stderr.strip().splitlines() or ["出力なし"])[-1]
    return False, f"採点テスト不合格: {last[:100]}"


def workspace_diff(task: Task, workspace: Path) -> str:
    def texts(root: Path) -> dict[str, list[str]]:
        return {
            str(p.relative_to(root)): p.read_text(encoding="utf-8", errors="replace").splitlines()
            for p in sorted(root.rglob("*"))
            if p.is_file() and not p.is_symlink() and "__pycache__" not in p.parts
        }

    before, after = texts(task.workspace), texts(workspace)
    out: list[str] = []
    for name in sorted(before.keys() | after.keys()):
        out += difflib.unified_diff(
            before.get(name, []), after.get(name, []), f"a/{name}", f"b/{name}", lineterm=""
        )
    return "\n".join(out) + "\n"


def run_case(
    task: Task,
    make_llm: Callable[[], OllamaClient],
    log_path: Path,
    num_ctx: int,
    max_steps: int,
    timeout: int,
    allow_all_commands: bool,
) -> dict:
    with tempfile.TemporaryDirectory() as tmp, log_path.open("w", encoding="utf-8") as log:
        workspace = Path(tmp) / "workspace"
        shutil.copytree(task.workspace, workspace, ignore=IGNORE)
        llm = make_llm()
        ui = EvalUI(log, allow_all_commands)
        agent = Agent(llm, ToolBox(workspace), ui, num_ctx, max_steps)
        started = time.monotonic()
        status = "完了"
        try:
            with time_limit(timeout):
                agent.run(task.prompt)
            if agent.hit_limit:
                status = "ステップ上限"
        except Deadline:
            status = "時間切れ"
        except LLMError as e:
            status = f"LLMエラー: {str(e)[:200]}"
        seconds = time.monotonic() - started
        passed, reason = grade(task, workspace)
        log_path.with_suffix(".diff").write_text(workspace_diff(task, workspace), encoding="utf-8")
        log.write(f"\n\n=== {status} / {'合格' if passed else '不合格 ' + reason}\n")
    stats = llm.stats
    speed = stats["output_tokens"] / stats["output_seconds"] if stats["output_seconds"] else 0
    return {
        "task": task.name,
        "passed": passed,
        "reason": reason,
        "status": status,
        "seconds": round(seconds, 1),
        "llm_calls": stats["calls"],
        "tool_calls": ui.tool_calls,
        "tool_errors": ui.tool_errors,
        "denied": ui.denied,
        "tokens_per_second": round(speed, 1),
    }
