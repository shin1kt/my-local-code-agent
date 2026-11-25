import unittest

from lru import LRUCache


class Check(unittest.TestCase):
    def test_capacity(self):
        for capacity in (0, -1):
            with self.assertRaises(ValueError):
                LRUCache(capacity)

    def test_eviction_and_order(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        self.assertEqual(list(c.keys()), ["b", "a"])
        self.assertEqual(c.get("a"), 1)
        c.put("c", 3)
        self.assertEqual(list(c.keys()), ["c", "a"])
        self.assertIsNone(c.get("b"))
        self.assertEqual(len(c), 2)

    def test_update(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.put("a", 9)
        self.assertEqual(len(c), 2)
        self.assertEqual(list(c.keys()), ["a", "b"])
        self.assertEqual(c.get("a"), 9)

    def test_default_and_none_value(self):
        c = LRUCache(1)
        self.assertEqual(c.get("x", 7), 7)
        c.put("n", None)
        self.assertIsNone(c.get("n", 7))
