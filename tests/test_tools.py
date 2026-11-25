import tempfile
import unittest
from pathlib import Path
from unittest import mock

from my_agent import tools
from my_agent.tools import ToolBox


class ToolBoxTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "ws"
        self.root.mkdir()
        (self.root / "a.txt").write_text("one\ntwo\ntwo\n")
        self.box = ToolBox(self.root)

    def run_tool(self, name, approve=True, **args):
        return self.box.run(name, args, lambda *_: approve)

    def test_rejects_paths_outside_workspace(self):
        outside = self.root.parent / "secret.txt"
        outside.write_text("secret")
        (self.root / "link").symlink_to(outside)
        for path in ("../secret.txt", str(outside), "link"):
            with self.subTest(path=path):
                self.assertIn("ワークスペース外", self.run_tool("read_file", path=path))
                self.assertIn("ワークスペース外", self.run_tool("write_file", path=path, content="x"))
        self.assertEqual(self.run_tool("search", pattern="secret"), "一致なし")
        self.assertEqual(outside.read_text(), "secret")

    def test_read_file_range(self):
        out = self.run_tool("read_file", path="a.txt", offset="2", limit=1)
        self.assertTrue(out.startswith("two\n"))
        self.assertIn("offset=3", out)

    def test_missing_file_suggests_same_name(self):
        self.assertIn("もしかして: a.txt", self.run_tool("read_file", path="src/a.txt"))

    def test_edit_requires_unique_match(self):
        self.assertIn("2 箇所", self.run_tool("edit_file", path="a.txt", old_text="two", new_text="x"))
        self.assertIn("見つかりません", self.run_tool("edit_file", path="a.txt", old_text="zzz", new_text="x"))
        self.run_tool("edit_file", path="a.txt", old_text="one", new_text="1")
        self.assertEqual((self.root / "a.txt").read_text(), "1\ntwo\ntwo\n")

    def test_edit_rejects_broken_indentation(self):
        source = "def f(x):\n    return 1 / x\n"
        (self.root / "f.py").write_text(source)
        edits = (
            ("return 1 / x", "if x:\n    return 1 / x\nreturn 0"),  # 行頭の空白を省略
            ("    return 1 / x", "    if x:\n    return 1"),  # 構文エラー
        )
        for old, new in edits:
            with self.subTest(new=new):
                out = self.run_tool("edit_file", path="f.py", old_text=old, new_text=new)
                self.assertTrue(out.startswith("ERROR"))
                self.assertEqual((self.root / "f.py").read_text(), source)
        # 単一行なら行の途中からの置換でよい
        out = self.run_tool("edit_file", path="f.py", old_text="return 1 / x", new_text="return x")
        self.assertIn("+    return x", out)

    def test_edit_keeps_crlf(self):
        (self.root / "crlf.txt").write_bytes(b"a\r\nb\r\n")
        self.run_tool("edit_file", path="crlf.txt", old_text="b", new_text="c")
        self.assertEqual((self.root / "crlf.txt").read_bytes(), b"a\r\nc\r\n")

    def test_denied_operations_have_no_effect(self):
        self.assertIn("拒否", self.run_tool("write_file", approve=False, path="new.txt", content="x"))
        self.assertIn("拒否", self.run_tool("run_command", approve=False, command="touch new.txt"))
        self.assertFalse((self.root / "new.txt").exists())

    def test_invalid_calls_become_errors(self):
        for name, args in (("nope", {}), ("read_file", {}), ("read_file", {"path": 1}), ("read_file", "x")):
            with self.subTest(name=name, args=args):
                self.assertTrue(self.box.run(name, args, lambda *_: True).startswith("ERROR"))

    def test_run_command(self):
        out = self.run_tool("run_command", command="cat a.txt; exit 3")
        self.assertIn("終了コード: 3", out)
        self.assertIn("one", out)

    def test_run_command_timeout(self):
        with mock.patch.object(tools, "COMMAND_TIMEOUT", 0.2):
            self.assertIn("タイムアウト", self.run_tool("run_command", command="sleep 30"))

    def test_output_is_truncated(self):
        (self.root / "big.txt").write_text("x" * 50_000)
        self.assertLess(len(self.run_tool("read_file", path="big.txt")), tools.MAX_OUTPUT + 100)


if __name__ == "__main__":
    unittest.main()
