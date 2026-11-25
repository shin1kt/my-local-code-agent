USERS = {1: {"name": "Alice", "group": "admin"}, 2: {"name": "Bob", "group": "staff"}}


def get_user(user_id):
    return USERS.get(user_id)


def get_user_names():
    return [user["name"] for user in USERS.values()]
