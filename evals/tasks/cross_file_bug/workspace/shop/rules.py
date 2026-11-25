# 数量割引: 10個以上で5%、50個以上で10%、100個以上で20%
TIERS = [(10, 5), (50, 10), (100, 20)]


def discount_rate(quantity):
    """数量に応じた割引率(%)。条件を満たす中で最も高い割引率を使う。"""
    for minimum, rate in TIERS:
        if quantity > minimum:
            return rate
    return 0
