import re
import unittest
from pathlib import Path

from app import auth, report, users


class Check(unittest.TestCase):
    def test_behavior(self):
        self.assertEqual(users.find_user_by_id(1)["name"], "Alice")
        self.assertEqual(users.get_user_names(), ["Alice", "Bob"])
        self.assertTrue(auth.is_admin(1))
        self.assertFalse(auth.is_admin(9))
        self.assertEqual(report.summary(2), "Bob (2 users)")

    def test_old_name_is_gone(self):
        for path in Path("app").rglob("*.py"):
            self.assertIsNone(re.search(r"\bget_user\b", path.read_text(encoding="utf-8")), path)
