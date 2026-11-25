import tempfile
import unittest
from pathlib import Path

from my_agent.agent import Agent
from my_agent.config import normalize_host
from my_agent.context import ELIDED, NUDGE, compact, estimate_tokens
from my_agent.llm import parse_text_tool_calls
from my_agent.tools import ToolBox
from my_agent.ui import printable


class FakeLLM:
    """台本どおりに応答するLLM。"""

    def __init__(self, replies):
        self.replies = iter(replies)
        self.seen = []

    def chat(self, messages, tools, on_text):
        self.seen.append(list(messages))
        return next(self.replies)


class FakeUI:
    def on_text(self, text): pass
    def on_tool_call(self, name, args): pass
    def on_tool_result(self, result): pass
    def approve(self, name, preview): return True


def call(name, **args):
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"function": {"name": name, "arguments": args}}],
    }


def say(text):
    return {"role": "assistant", "content": text}


class AgentTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def agent(self, replies, max_steps=10):
        self.llm = FakeLLM(replies)
        return Agent(self.llm, ToolBox(self.root), FakeUI(), 32768, max_steps)

    def test_runs_tools_until_final_answer(self):
        agent = self.agent([call("write_file", path="a.txt", content="hi"), say("完了")])
        self.assertEqual(agent.run("作って"), "完了")
        self.assertEqual((self.root / "a.txt").read_text(), "hi")
        self.assertEqual(self.llm.seen[1][-1]["role"], "tool")

    def test_tool_error_is_returned_to_llm(self):
        agent = self.agent([call("read_file", path="none"), call("list_files"), say("ありません")])
        agent.run("読んで")
        self.assertTrue(self.llm.seen[1][-1]["content"].startswith("ERROR"))

    def test_nudges_limited_times_after_failure(self):
        agent = self.agent([call("run_command", command="false")] + [say("諦めます")] * 3)
        self.assertEqual(agent.run("x"), "諦めます")
        self.assertEqual(len(self.llm.seen), 4)

    def test_command_failure_persists_across_other_tools(self):
        agent = self.agent(
            [call("run_command", command="false"), call("list_files"), say("直します"),
             call("run_command", command="true"), say("完了")]
        )
        self.assertEqual(agent.run("x"), "完了")

    def test_does_not_nudge_after_denial(self):
        agent = self.agent([call("run_command", command="true"), say("やめます")])
        agent.ui.approve = lambda *_: False
        agent.run("x")
        self.assertEqual(len(self.llm.seen), 2)

    def test_system_prompt_lists_files(self):
        (self.root / "main.py").touch()
        self.assertIn("main.py", self.agent([]).messages[0]["content"])

    def test_repeated_call_is_blocked(self):
        agent = self.agent([call("list_files")] * 4 + [call("search", pattern="x"), say("終わり")])
        agent.run("x")
        self.assertIn("繰り返し", self.llm.seen[4][-1]["content"])

    def test_stops_at_max_steps(self):
        agent = self.agent([call("list_files")] * 2, max_steps=2)
        self.assertIn("上限", agent.run("x"))
        self.assertTrue(agent.hit_limit)


class CompactTest(unittest.TestCase):
    def test_elides_old_tool_results_first(self):
        messages = [say("sys") | {"role": "system"}, {"role": "user", "content": "q"}]
        messages += [{"role": "tool", "content": "x" * 4000} for _ in range(6)]
        result = compact(messages, 5000)
        self.assertLessEqual(estimate_tokens(result), 5000)
        self.assertEqual(result[2]["content"], ELIDED)
        self.assertEqual(result[-1], messages[-1])
        self.assertNotEqual(messages[2]["content"], ELIDED)  # 元の履歴は変更しない

    def test_drops_old_turns_but_keeps_current_request(self):
        messages = [{"role": "system", "content": "sys"}]
        for i in range(5):
            messages += [{"role": "user", "content": f"q{i}"}, say("あ" * 1000)]
        messages.append({"role": "user", "content": "now"})
        result = compact(messages, 1500)
        self.assertEqual(result[0]["role"], "system")
        self.assertEqual(result[-1]["content"], "now")
        self.assertLessEqual(estimate_tokens(result), 1500)


    def test_nudge_does_not_count_as_request(self):
        messages = [{"role": "system", "content": "sys"}]
        messages += [{"role": "user", "content": "now"}, say("あ" * 3000), {"role": "user", "content": NUDGE}]
        self.assertIn({"role": "user", "content": "now"}, compact(messages, 1000))


class NormalizeHostTest(unittest.TestCase):
    def test_adds_scheme_and_port(self):
        for host in ("localhost", "localhost:11434", "http://localhost:11434/"):
            self.assertEqual(normalize_host(host), "http://localhost:11434")


class ParseTextToolCallsTest(unittest.TestCase):
    CALL = '{"name": "read_file", "arguments": {"path": "a"}}'

    def parse(self, text):
        return parse_text_tool_calls(text, {"read_file"})

    def test_accepts_bare_fenced_and_tagged_json(self):
        for text in (self.CALL, f"```json\n{self.CALL}\n```", f"読みます<tool_call>\n{self.CALL}\n</tool_call>"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text)[0]["function"]["arguments"], {"path": "a"})

    def test_ignores_examples_and_unknown_tools(self):
        for text in (f"例:\n```json\n{self.CALL}\n```\nです", '{"name": "rm", "arguments": {}}', "こんにちは", "[1]"):
            with self.subTest(text=text):
                self.assertEqual(self.parse(text), [])


class PrintableTest(unittest.TestCase):
    def test_escapes_control_sequences(self):
        self.assertEqual(printable("日本語\n\x1b[2K\r"), "日本語\n\\x1b[2K\\r")


if __name__ == "__main__":
    unittest.main()
