import intern.dbc as dbc
import intern.helper as h
import intern.database as db


def get_user_hash_by_name(name: str) -> str:
    """
    Retrieves a user hash by their name.

    Args:
        name (str): The name of the user.

    Returns:
        str: The hash of the user.

    Raises:
        Raises an error if the user is not found.
    """
    hash = h.opt_hash_by_key_value_and_version(db._user, name, "latest")
    dbc.assert_true(hash, {"msg": "NOT_FOUND", "kind": "user", "name": name})
    return hash


def get_user_by_hash(hash: str) -> dict:
    """
    Retrieves a user by their hash.

    Args:
        hash (str): The hash of the user.

    Returns:
        dict: The user object.

    Raises:
        Raises an error if the user is not found.
    """
    user = db._user[hash]
    dbc.assert_true(user, {"msg": "NOT_FOUND", "kind": "user", "name": hash})
    return user


def login(name: str) -> str:
    """
    Logs in a user by their name.
    If the user is not found, it raises an error.

    Args:
        name (str): The name of the user.

    Returns:
        str: The hash of the user.
    """
    return get_user_hash_by_name(name)


def add_user(user: dict, logged_in_user: str) -> str:
    """
    Adds a new user to the database.

    Args:
        user (dict): User details.
        logged_in_user (str): The user performing the operation.

    Returns:
        str: The hash of the stored user.

    Raises:
        Raises an error if the user is not a superuser or already exists.
    """
    creating_user = get_user_by_hash(logged_in_user)
    if not creating_user["su"]:
        dbc.raise_error({"msg": "MUST_BE_SUPERUSER"})
    h.validate_user_input(user, "user_def")

    version = h.get_next_free_version(db._user, user["name"])
    dbc.assert_true(version == 1, {"msg": "USER_ALREADY_EXISTS", "name": user["name"]})

    return db.enrich_and_store_in_table(db._user, user, logged_in_user)

