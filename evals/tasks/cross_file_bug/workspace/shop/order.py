from shop.pricing import discounted


def total(items):
    """items は (単価, 数量) のリスト。"""
    return sum(discounted(price, quantity) for price, quantity in items)
