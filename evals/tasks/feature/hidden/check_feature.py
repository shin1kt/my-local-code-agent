import unittest

from text_utils import slugify, truncate


class Check(unittest.TestCase):
    def test_slugify(self):
        for text, expected in (
            ("Hello, World!", "hello-world"),
            ("  a -- b  ", "a-b"),
            ("snake_case 2", "snake-case-2"),
            ("café au lait", "caf-au-lait"),
            ("日本語 Text", "text"),
        ):
            self.assertEqual(slugify(text), expected)

    def test_empty(self):
        for text in ("", "!!!", "日本語"):
            with self.assertRaises(ValueError):
                slugify(text)

    def test_existing(self):
        self.assertEqual(truncate("abcdefgh", 6), "abc...")
