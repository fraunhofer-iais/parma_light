import re
import secrets

import intern.dbc as dbc
import intern.helper as h
import intern.database as db

def login(name: str, password: str) -> str:
    """
    Logs in a user by name and password.
    Returns a session token on success.
    """
    dbc.assert_true(_verify_user(name, password), {"msg": "INVALID_PASSWORD"})
    user_hash = _get_user_hash_by_name(name)
    token = secrets.token_hex(32)
    _sessions[token] = user_hash
    return token


def logout(token: str) -> None:
    """Invalidate a session token."""
    _sessions.pop(token, None)


def add(user: dict, logged_in_user: str) -> str:
    """
    Adds a new user to the database.
    The 'user' dict must contain 'name', 'admin', and 'password'.
    The password is hashed before storage; the plain-text value is removed.
    """
    creating_user = _get_user_by_hash(logged_in_user)
    if not creating_user["admin"]:
        dbc.raise_error({"msg": "MUST_BE_ADMIN"})
    h.validate_user_input(user, "user_def")

    version = h.get_next_free_version(db._user, user["name"])
    dbc.assert_true(version == 1, {"msg": "USER_ALREADY_EXISTS", "name": user["name"]})

    plain_password = user.pop("password")
    user["_password_hash"] = h.make_password_hash(plain_password)

    return db.enrich_and_store_in_table(db._user, user, logged_in_user)


def remove(user_to_remove, calling_user_hash):
    dbc.assert_true(bool(user_to_remove), {"msg": "INVALID_NAME"})
    calling_user = _get_user_by_hash(calling_user_hash)
    dbc.assert_true(calling_user.get("admin", False), {"msg": "MUST_BE_ADMIN"})
    hash_of_user_to_remove = _get_user_hash_by_name(user_to_remove)
    dbc.assert_true(calling_user_hash != hash_of_user_to_remove, {"msg": "USER_NO_DELETE", "name": user_to_remove})
    with db._table_mutex:
        del db._user[hash_of_user_to_remove]
        db._min_unique_prefix_length = None
    _remove_sessions_of(hash_of_user_to_remove)


def change_password(user_hash: str, old_password: str, new_password: str) -> None:
    """
    Changes the password for the user identified by user_hash.
    Verifies passwords before applying the change.
    Replaces the existing entry in-place (version stays 1), see _replace_user_entry.
    """
    stored_user = _get_user_by_hash(user_hash)
    dbc.assert_true(_verify_user(stored_user["name"], old_password), {"msg": "INVALID_PASSWORD"})
    dbc.assert_true(bool(new_password), {"msg": "INVALID_PASSWORD"})

    new_entry = dict(stored_user)
    new_entry["_password_hash"] = h.make_password_hash(new_password)
    _replace_user_entry(user_hash, new_entry)


def get_user_hash_from_session_token(token: str) -> str:
    """Resolve a session token to a user hash. Raises if the token is unknown."""
    user_hash = _sessions.get(token)
    dbc.assert_true(bool(user_hash), {"msg": "TOKEN_INVALID"})
    return user_hash


# helper

_ALPHANUMERIC_PATTERN = re.compile("^[a-zA-Z][a-zA-Z0-9_]*$")
_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_äöüÄÖÜß@-]{2,64}$')

_sessions: dict = {} # in-memory session store: token → user_hash


def _replace_user_entry(user_hash: str, new_entry: dict) -> str:
    """
    Replaces a user entry in-place (the version is unchanged): removes the old hash key, stores the
    new entry under its new hash, updates the active sessions referencing the old hash and stores
    the tables. Returns the new hash.
    """
    new_hash = h.make_git_like_hash_of_json(new_entry)
    with db._table_mutex:
        del db._user[user_hash]
        db._user[new_hash] = new_entry
        db._min_unique_prefix_length = None
    for token, h_val in list(_sessions.items()):
        if h_val == user_hash:
            _sessions[token] = new_hash
    db.store_tables()
    return new_hash


def _remove_sessions_of(user_hash: str) -> None:
    """invalidates all session tokens of a user"""
    for token in [t for t, h_val in _sessions.items() if h_val == user_hash]:
        del _sessions[token]


def is_alphanumeric(to_test: str):
    dbc.assert_true(_ALPHANUMERIC_PATTERN.match(to_test),
                    {"msg": "REGEX_ERROR", "content": to_test})


def _get_user_by_hash(hash: str) -> dict:
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


def _get_user_hash_by_name(name: str) -> str:
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


def _check_user_name_valid(name: str):
    if not _USERNAME_RE.match(name):
        dbc.raise_error({"msg": "INVALID_NAME"})


def _verify_user(name: str, password: str) -> bool:
    """
    Check whether a user exists, is active, and the password is correct.

    Args:
        name (str): User name to verify.
        password (str): Plain-text password to check.

    Returns:
        bool: ``True`` if the credentials are valid and the account is
                active, ``False`` otherwise.
    """
    _check_user_name_valid(name)
    user_hash = _get_user_hash_by_name(name)
    stored_user = _get_user_by_hash(user_hash)
    pw_hash = stored_user.get("_password_hash")
    return h.verify_password_hash(password, pw_hash)