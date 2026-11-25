from app.users import get_user


def is_admin(user_id):
    user = get_user(user_id)
    return user is not None and user["group"] == "admin"
