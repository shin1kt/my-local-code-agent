import unittest

from shop.order import total
from shop.rules import discount_rate


class Check(unittest.TestCase):
    def test_every_tier(self):
        expected = {0: 0, 9: 0, 10: 5, 49: 5, 50: 10, 99: 10, 100: 20, 500: 20}
        self.assertEqual({q: discount_rate(q) for q in expected}, expected)

    def test_total(self):
        self.assertEqual(total([(100, 50), (33, 10)]), 4813)
