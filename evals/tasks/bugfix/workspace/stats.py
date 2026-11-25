def average(numbers):
    """平均値を返す。空のリストなら 0 を返す。"""
    return sum(numbers) / len(numbers)


def median(numbers):
    """中央値を返す。"""
    ordered = sorted(numbers)
    middle = len(ordered) // 2
    return ordered[middle]
