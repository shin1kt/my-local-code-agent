from app import users


def summary(user_id):
    user = users.get_user(user_id)
    if user is None:
        return "unknown"
    return f"{user['name']} ({len(users.get_user_names())} users)"
