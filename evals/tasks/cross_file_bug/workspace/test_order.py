import unittest

from shop.order import total


class OrderTest(unittest.TestCase):
    def test_no_discount(self):
        self.assertEqual(total([(100, 9)]), 900)

    def test_boundary(self):
        self.assertEqual(total([(100, 10)]), 950)

    def test_large(self):
        self.assertEqual(total([(100, 120)]), 9600)


if __name__ == "__main__":
    unittest.main()
