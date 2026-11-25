from shop.rules import discount_rate


def discounted(price, quantity):
    """割引後の小計(円未満切り捨て)。"""
    return price * quantity * (100 - discount_rate(quantity)) // 100
