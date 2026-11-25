import unittest

from stats import average, median


class Check(unittest.TestCase):
    def test_values(self):
        self.assertEqual(average([]), 0)
        self.assertEqual(average([1, 2]), 1.5)
        self.assertEqual(median([10, 1, 4, 3, 2, 7]), 3.5)
        self.assertEqual(median([5]), 5)

    def test_input_is_not_mutated(self):
        data = [3, 1, 2]
        median(data)
        self.assertEqual(data, [3, 1, 2])
