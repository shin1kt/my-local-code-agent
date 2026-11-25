import shutil
import tempfile
import unittest
from pathlib import Path

from evals.harness import IGNORE, grade, is_safe_command, load_tasks, run_case


class FakeLLM:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.stats = {"calls": 0, "prompt_tokens": 0, "output_tokens": 0, "output_seconds": 0.0}

    def chat(self, messages, tools, on_text):
        return next(self.replies)


SOLUTIONS = {
    "bugfix": {
        "stats.py": "def average(n):\n    return sum(n) / len(n) if n else 0\n\n\ndef median(n):\n"
        "    o, m = sorted(n), len(n) // 2\n    return o[m] if len(o) % 2 else (o[m - 1] + o[m]) / 2\n"
    },
    "feature": {
        "text_utils.py": "import re\n\n\ndef truncate(t, n):\n    return t if len(t) <= n else t[: n - 3] + '...'\n\n\n"
        "def slugify(t):\n    s = re.sub('[^a-z0-9]+', '-', t.lower()).strip('-')\n"
        "    if not s:\n        raise ValueError\n    return s\n"
    },
    "cross_file_bug": {
        "shop/rules.py": "def discount_rate(q):\n    return 20 if q >= 100 else 10 if q >= 50 else 5 if q >= 10 else 0\n"
    },
    "from_spec": {
        "lru.py": "class LRUCache:\n    def __init__(self, c):\n        if c < 1:\n            raise ValueError\n"
        "        self.c, self.d = c, {}\n    def get(self, k, default=None):\n        if k not in self.d:\n"
        "            return default\n        self.d[k] = self.d.pop(k)\n        return self.d[k]\n"
        "    def put(self, k, v):\n        self.d.pop(k, None)\n        self.d[k] = v\n"
        "        if len(self.d) > self.c:\n            del self.d[next(iter(self.d))]\n"
        "    def keys(self):\n        return list(self.d)[::-1]\n    def __len__(self):\n        return len(self.d)\n"
    },
}


class GradeTest(unittest.TestCase):
    """どの課題も、未着手なら不合格、正解なら合格になることを確かめる。"""

    def copy(self, task):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        target = Path(tmp.name) / "ws"
        shutil.copytree(task.workspace, target, ignore=IGNORE)
        return target

    def test_all_tasks(self):
        for task in load_tasks():
            with self.subTest(task=task.name):
                ws = self.copy(task)
                self.assertFalse(grade(task, ws)[0])
                if task.name == "rename":
                    for f in ws.rglob("*.py"):
                        f.write_text(f.read_text().replace("get_user(", "find_user_by_id(")
                                     .replace("import get_user\n", "import find_user_by_id\n"))
                else:
                    for name, content in SOLUTIONS[task.name].items():
                        (ws / name).write_text(content)
                self.assertEqual(grade(task, ws), (True, ""))

    def test_tampering_fails_even_if_solved(self):
        (task,) = load_tasks(["bugfix"])
        ws = self.copy(task)
        (ws / "stats.py").write_text(SOLUTIONS["bugfix"]["stats.py"])
        with (ws / "test_stats.py").open("a") as f:
            f.write("# x\n")
        self.assertIn("test_stats.py", grade(task, ws)[1])


class SafeCommandTest(unittest.TestCase):
    def test_allowed(self):
        for c in ("python3 -m unittest", "python3 -m unittest -v test_a 2>&1", "pytest test_a.py", "ls -la", "python3 app.py x"):
            self.assertTrue(is_safe_command(c), c)

    def test_rejected(self):
        for c in (
            "rm -rf x", "ls; rm x", "cat a > b", "cat /etc/passwd", "cat ../a", "cat ~/a", "ls $(id)", "ls\nid", "ls 2>&1; id",
            "python3 -c 'x'", "pip install x", "find . -delete", "pytest --rootdir=/etc", "cat '/etc/passwd'", "lsof",
        ):
            self.assertFalse(is_safe_command(c), c)


class RunCaseTest(unittest.TestCase):
    def test_runs_and_grades(self):
        (task,) = load_tasks(["bugfix"])
        reply = {"role": "assistant", "content": "", "tool_calls": [{"function": {
            "name": "write_file",
            "arguments": {"path": "stats.py", "content": SOLUTIONS["bugfix"]["stats.py"]}}}]}
        denied = {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "run_command", "arguments": {"command": "rm -rf ."}}}]}
        done = {"role": "assistant", "content": "done"}
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "x.log"
            r = run_case(task, lambda: FakeLLM([denied, reply, done]), log, 8192, 5, 30, False)
            self.assertTrue(log.with_suffix(".diff").read_text())
        self.assertTrue(r["passed"])
        self.assertEqual((r["tool_calls"], r["denied"]), (2, 1))


if __name__ == "__main__":
    unittest.main()
