"""エージェントが使うツール群。

失敗は ToolError で表し、ToolBox.run() が "ERROR: ..." という文字列にして
LLM に返す。LLM がエラーを読んで自分でやり直せるようにするため。
"""
from __future__ import annotations

import ast
import difflib
import os
import re
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

MAX_OUTPUT = 12_000  # ツール結果1件の最大文字数
MAX_FILE_BYTES = 1_000_000
COMMAND_TIMEOUT = 120
IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


DENIED = "ERROR: ユーザーがこの操作を拒否しました。"
EXIT_CODE = "終了コード: "  # agent.py がコマンドの成否判定に使う


class ToolError(Exception):
    pass


@dataclass
class Tool:
    name: str
    description: str
    properties: dict[str, dict]
    required: list[str]
    run: Callable[..., str]
    # 副作用のあるツールだけが持つ。ユーザーに承認を求めるときの表示内容を返す。
    preview: Callable[..., str] | None = None

    @property
    def needs_approval(self) -> bool:
        return self.preview is not None

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.properties,
                    "required": self.required,
                },
            },
        }

    def validate(self, args: Any) -> dict:
        if not isinstance(args, dict):
            raise ToolError("引数はJSONオブジェクトで指定してください")
        missing = [k for k in self.required if k not in args]
        if missing:
            raise ToolError(f"必須の引数がありません: {', '.join(missing)}")
        clean = {}
        for key, spec in self.properties.items():
            if key not in args or (args[key] is None and key not in self.required):
                continue
            value = args[key]
            if spec["type"] == "integer":
                try:
                    value = int(value)  # "10" のように文字列で渡すモデルがある
                except (TypeError, ValueError):
                    raise ToolError(f"{key} は整数で指定してください") from None
            elif not isinstance(value, str):
                raise ToolError(f"{key} は文字列で指定してください")
            clean[key] = value
        return clean


def check_syntax(path: str, old: str, new: str) -> None:
    """正しかったPythonファイルを構文エラーにする編集を拒否する。

    小さいモデルは自分で壊したインデントを直せないことが多く、壊れる前に止める。
    """
    if not path.endswith(".py"):
        return
    try:
        ast.parse(old)
    except (SyntaxError, ValueError):
        return
    try:
        ast.parse(new)
    except (SyntaxError, ValueError) as e:
        raise ToolError(
            f"この編集をすると構文エラーになるため適用しませんでした: {e}。"
            "old_text と new_text の両方を行頭の空白から書き、インデントを確認してください"
        ) from None


def truncate(text: str) -> str:
    """先頭と末尾を残して切り詰める(テスト結果などは末尾が重要なため)。"""
    if len(text) <= MAX_OUTPUT:
        return text
    half = MAX_OUTPUT // 2
    return f"{text[:half]}\n... [{len(text) - MAX_OUTPUT} 文字省略] ...\n{text[-half:]}"


class ToolBox:
    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()
        self.tools = {t.name: t for t in self._build()}

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self.tools.values()]

    def run(self, name: str, args: Any, approve: Callable[[str, str], bool]) -> str:
        """ツールを1つ実行する。approve(ツール名, プレビュー) が False なら実行しない。"""
        try:
            tool = self.tools.get(name)
            if tool is None:
                raise ToolError(f"不明なツールです: {name}(使えるツール: {', '.join(self.tools)})")
            args = tool.validate(args)
            if tool.preview is not None and not approve(name, tool.preview(**args)):
                return DENIED + "同じ操作を繰り返さず、どうするか確認してください。"
            return truncate(tool.run(**args)) or "(出力なし)"
        except ToolError as e:
            return f"ERROR: {e}"
        except (OSError, ValueError) as e:
            return f"ERROR: {type(e).__name__}: {e}"

    # --- パスの扱い ---

    def _resolve(self, path: str) -> Path:
        """ワークスペース外へのアクセスを拒否する(.. やシンボリックリンクは解決後に判定)。"""
        full = (self.workspace / path).resolve()
        if not full.is_relative_to(self.workspace):
            raise ToolError(f"ワークスペース外にはアクセスできません: {path}")
        return full

    def _read(self, path: str) -> str:
        full = self._resolve(path)
        if not full.is_file():
            same_name = [f for f in self._walk(self.workspace) if Path(f).name == full.name]
            hint = f"。もしかして: {', '.join(same_name[:5])}" if same_name else ""
            raise ToolError(f"ファイルがありません: {path}{hint}")
        if full.stat().st_size > MAX_FILE_BYTES:
            raise ToolError(f"ファイルが大きすぎます: {path}")
        try:
            # バイト列から変換し、CRLF などの改行コードをそのまま保つ
            return full.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            raise ToolError(f"UTF-8のテキストファイルではありません: {path}") from None

    def _walk(self, start: Path) -> Iterator[str]:
        """start 以下のファイルをワークスペースからの相対パスで列挙する。"""
        if start.is_file():
            yield str(start.relative_to(self.workspace))
            return
        for root, dirs, files in os.walk(start):
            dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIRS)
            for f in sorted(files):
                yield str((Path(root) / f).relative_to(self.workspace))

    # --- 読み取り系ツール ---

    def list_files(self, path: str = ".") -> str:
        start = self._resolve(path)
        if not start.exists():
            raise ToolError(f"パスがありません: {path}")
        files = list(self._walk(start))
        more = f"\n... 他 {len(files) - 300} 件" if len(files) > 300 else ""
        return "\n".join(files[:300]) + more

    def read_file(self, path: str, offset: int = 1, limit: int = 400) -> str:
        # 行番号は付けない。付けると edit_file の old_text に混ぜてしまうモデルが多い。
        lines = self._read(path).splitlines(keepends=True)
        start = max(offset, 1) - 1
        end = start + max(limit, 1)
        text = "".join(lines[start:end])
        if end < len(lines):
            text += f"\n... [全 {len(lines)} 行中 {end} 行目まで表示。続きは offset={end + 1}]"
        return text

    def search(self, pattern: str, path: str = ".") -> str:
        try:
            regex = re.compile(pattern)
        except re.error as e:
            raise ToolError(f"正規表現が不正です: {e}") from None
        start = self._resolve(path)
        if not start.exists():
            raise ToolError(f"パスがありません: {path}")
        hits = []
        for name in self._walk(start):
            try:
                text = self._read(name)
            except (ToolError, OSError):
                continue  # バイナリやワークスペース外へのリンク
            for number, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    hits.append(f"{name}:{number}: {line.strip()[:200]}")
                    if len(hits) >= 100:
                        return "\n".join(hits) + "\n... (100件で打ち切り)"
        return "\n".join(hits) or "一致なし"

    # --- 書き込み系ツール ---

    def _write(self, path: str, content: str) -> None:
        full = self._resolve(path)
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content.encode("utf-8"))

    def _diff(self, path: str, old: str, new: str) -> str:
        lines = difflib.unified_diff(
            old.splitlines(), new.splitlines(), f"a/{path}", f"b/{path}", lineterm=""
        )
        return "\n".join(lines) or f"{path} (表示できる差分なし)"

    def write_file(self, path: str, content: str) -> str:
        self._write(path, content)
        return f"{path} を書き込みました"

    def _preview_write(self, path: str, content: str) -> str:
        full = self._resolve(path)
        if full.is_dir():
            raise ToolError(f"ディレクトリです: {path}")
        old = self._read(path) if full.exists() else ""
        check_syntax(path, old, content)
        return self._diff(path, old, content)

    def _edited(self, path: str, old_text: str, new_text: str) -> tuple[str, str]:
        content = self._read(path)
        if not old_text:
            raise ToolError("old_text が空です。新規作成には write_file を使ってください")
        if old_text == new_text:
            raise ToolError("old_text と new_text が同じです")
        count = content.count(old_text)
        if count == 0:
            raise ToolError("old_text が見つかりません。read_file で現在の内容を確認し、空白や改行も正確に写してください")
        if count > 1:
            raise ToolError(f"old_text が {count} 箇所に一致します。前後の行を含めて一意にしてください")
        line_start = content.rfind("\n", 0, content.index(old_text)) + 1
        prefix = content[line_start : content.index(old_text)]
        if prefix and prefix.isspace() and "\n" in new_text:
            # 行頭の空白を省いたまま複数行に置き換えると、2行目以降のインデントがずれる
            raise ToolError(
                f"複数行に置き換えるときは、old_text と new_text を行頭の空白(この行は {prefix!r})から書いてください"
            )
        edited = content.replace(old_text, new_text)
        check_syntax(path, content, edited)
        return content, edited

    def edit_file(self, path: str, old_text: str, new_text: str) -> str:
        old, new = self._edited(path, old_text, new_text)
        self._write(path, new)
        return f"{path} を編集しました\n{self._diff(path, old, new)}"

    def _preview_edit(self, path: str, old_text: str, new_text: str) -> str:
        return self._diff(path, *self._edited(path, old_text, new_text))

    def run_command(self, command: str) -> str:
        # 注意: 作業ディレクトリを指定しているだけで、隔離(サンドボックス化)はしていない。
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=self.workspace,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            out, _ = proc.communicate(timeout=COMMAND_TIMEOUT)
        except BaseException as e:  # タイムアウトや Ctrl-C では子プロセスごと止める
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.stdout.close()
            proc.wait()
            if isinstance(e, subprocess.TimeoutExpired):
                raise ToolError(f"{COMMAND_TIMEOUT} 秒でタイムアウトしました") from None
            raise
        return f"{EXIT_CODE}{proc.returncode}\n{out.decode(errors='replace')}"

    def _build(self) -> list[Tool]:
        def s(description: str) -> dict:
            return {"type": "string", "description": description}

        def i(description: str) -> dict:
            return {"type": "integer", "description": description}

        path = s("ワークスペースからの相対パス")
        return [
            Tool("list_files", "ファイルを再帰的に一覧表示する。", {"path": path}, [], self.list_files),
            Tool(
                "read_file",
                "テキストファイルを読む。",
                {"path": path, "offset": i("開始行(1始まり)"), "limit": i("最大行数")},
                ["path"],
                self.read_file,
            ),
            Tool(
                "search",
                "正規表現でファイルの内容を検索する。",
                {"pattern": s("Pythonの正規表現"), "path": path},
                ["pattern"],
                self.search,
            ),
            Tool(
                "write_file",
                "ファイルを新規作成、または全体を上書きする。既存ファイルの一部変更には edit_file を使う。",
                {"path": path, "content": s("ファイル全体の内容")},
                ["path", "content"],
                self.write_file,
                self._preview_write,
            ),
            Tool(
                "edit_file",
                "既存ファイルの一部を置き換える。old_text はファイル内で1箇所だけに完全一致する必要がある。",
                {"path": path, "old_text": s("置き換え前の文字列"), "new_text": s("置き換え後の文字列")},
                ["path", "old_text", "new_text"],
                self.edit_file,
                self._preview_edit,
            ),
            Tool(
                "run_command",
                "ワークスペースでシェルコマンドを実行する(テスト実行など)。対話的なコマンドは使えない。",
                {"command": s("シェルコマンド")},
                ["command"],
                self.run_command,
                lambda command: f"$ {command}",
            ),
        ]
