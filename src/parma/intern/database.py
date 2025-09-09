import os
import json
from pathlib import Path
import random
import shutil
import string

from intern import msg
import intern.helper as h
import intern.dbc as dbc

datastore_dir = None
data_dir = None
temp_dir = None
tables = None

_user = None
_data = None
_node = None
_workflow = None
_run = None

def init_globals(parma_base_directory: Path) -> None:
    """
    Initializes global variables and loads all database tables from JSON files.

    Args:
        parma_base_directory (str): The base directory where the database JSON files are stored
            and the directories for data files and temp files are found.

    Returns:
        None
    """
    global datastore_dir, data_dir, temp_dir, _user, _data, _node, _workflow, _run, tables
    datastore_dir = parma_base_directory
    data_dir = datastore_dir / "data_dir"
    temp_dir = datastore_dir / "temp_dir"
    msg.print({"msg": "BASE_DIRECTORY", "name": datastore_dir})

    _user = _load_json("user")
    _data = _load_json("data")
    _node = _load_json("node")
    _workflow = _load_json("workflow")
    _run = _load_json("run")

    tables = {
        "user": _user,
        "data": _data,
        "node": _node,
        "workflow": _workflow,
        "run": _run
    }


def store_tables() -> None:
    """
    Stores all tables into their respective JSON files in the base directory.

    Returns:
        None
    """
    for name, dictionary in tables.items():
        file_path = os.path.join(datastore_dir, f"{name}.json")
        h.set_file_writable(file_path)
        with open(file_path, "w") as f:
            json.dump(dictionary, f, indent=4, sort_keys=True)
        h.set_file_readonly(file_path)
        msg.print({"msg": "STORED_TABLE", "name": name})


def enrich_and_store_in_table(table_dict: dict, entry: dict, logged_in_user: str) -> str:
    """
    Stores an entry (user, data, node, workflow, run) in its table.
    Creates the _version, _date, _hash_of_creating_user metadata properties.

    Args:
        table_dict (dict): The table to store the entry into.
        entry (dict): Entry to be enriched and stored.
        logged_in_user (str): The user performing the operation.

    Returns:
        str: The hash of the stored entry.
    """
    global _min_unique_prefix_length
    version = h.get_next_free_version(table_dict, entry["name"])
    entry["_version"] = version
    entry["_date"] = h.get_date()
    entry["_hash_of_creating_user"] = logged_in_user
    hash = h.make_git_like_hash_of_json(entry)
    table_dict[hash] = entry
    _min_unique_prefix_length = None # recompute when needed in the future
    return hash


def _load_json(path: str) -> dict:
    """
    Loads a JSON file from the base directory.

    Args:
        path (str): The name of the JSON file (without extension).

    Returns:
        dict: The loaded JSON data.
    """
    with open(datastore_dir / (path + ".json"), 'r') as file:
        return json.load(file)


# the current length that is needed to identify a SHA-1 hash uniquely
_min_unique_prefix_length = None
_last_min_unique_prefix_length = None
_current_hashes = None


def get_min_unique_prefix_length() -> int:
    """
    Returns the minimum unique prefix length required to identify a SHA-1 hash.

    Returns:
        int: The minimum unique prefix length.
    """
    _opt_recompute_min_unique_prefix_length()
    return _min_unique_prefix_length


def _opt_recompute_min_unique_prefix_length() -> None:
    """
    Recomputes the minimum unique prefix length if necessary.

    Returns:
        None
    """
    global _min_unique_prefix_length, _last_min_unique_prefix_length, _current_hashes
    if not _min_unique_prefix_length:
        _current_hashes = _collect_hashes_from_db()
        len = _compute_min_unique_prefix_length(_current_hashes)
        len = len if len >= 6 else 6
        _min_unique_prefix_length = len if len % 2 == 0 else len + 1
        if _last_min_unique_prefix_length and _min_unique_prefix_length != _last_min_unique_prefix_length:
            msg.print({"msg":"NUMBER_HEX_DIGITS", "number": _min_unique_prefix_length})
            _last_min_unique_prefix_length = _min_unique_prefix_length


def get_hash_from_prefix(prefix: str, table: dict = None) -> str:
    """
    Returns the full hash from current_hashes that starts with the given prefix.
    If not exactly one match is found, raises an error.

    Args:
        prefix (str): The prefix of the hash.
        table (dict, optional): The table to search in. If None, searches all current hashes.

    Returns:
        str: The full hash matching the prefix.
    """
    if table == None:
        _opt_recompute_min_unique_prefix_length()
        matches = [h for h in _current_hashes if h.startswith(prefix)]
        if not matches or len(matches) > 1:
            dbc.raise_error({"msg": "INVALID_HASH", "prefix": prefix})
        return matches[0]
    else:
        matches = [h for h in table.keys() if h.startswith(prefix)]
        if not matches or len(matches) > 1:
            dbc.raise_error({"msg": "INVALID_HASH", "prefix": prefix})
        return matches[0]


def shrink_hash(hash: str) -> str:
    """
    Returns the shortest unique prefix of a hash.

    Args:
        hash (str): The full hash.

    Returns:
        str: The unique prefix of the hash.
    """
    if hash:
        prefix_length = get_min_unique_prefix_length()
        return hash[:prefix_length]
    else:
        return "---"


def assert_user_exists(authentification_token: str) -> None:
    """
    Asserts that a user exists.
    Raises an error if user is not found. Reason probably, that user was not logged in.

    Args:
        authentification_token (str): The authentication token to check.

    Returns:
        None
    """
    dbc.assert_true(authentification_token in _user, {"msg": "NO_USER_LOGGED_IN"})
    return authentification_token


def _compute_min_unique_prefix_length(hashes: set[str]) -> int:
    """
    Determines the minimum number of hex digits required to uniquely identify each SHA-1 hash in a set.

    Args:
        hashes (set[str]): A set of SHA-1 hash strings (40 hex digits each).

    Returns:
        int: The smallest prefix length (number of hex digits) such that all hashes are uniquely identified by their prefix.
             Returns 40 if all 40 digits are needed.
    """
    for length in range(1, 41):
        prefixes = set(h[:length] for h in hashes)
        if len(prefixes) == len(hashes):
            return length
    return 40


def _collect_hashes_from_db() -> set:
    """
    Collects all hashes from the user, data, node, workflow, and run tables, including content hashes from data.

    Returns:
        set: A set of all hashes.
    """
    hashes = set()
    hashes.update(_user.keys())
    hashes.update(_data.keys())
    hashes.update(_node.keys())
    hashes.update(_workflow.keys())
    hashes.update(_run.keys())
    for data in _data.values():
        if "_hash_of_content" in data:
            hashes.add(data["_hash_of_content"])
    return hashes


def create_a_temp_directory(length: int = 8) -> str:
    """
    Creates and returns a new temporary directory.

    Args:
        length (int, optional): Length of the random directory name. Default is 8.

    Returns:
        str: The path to the created temporary directory.
    """
    while True:
        rand_name = ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))
        path = os.path.join(temp_dir, rand_name)
        try:
            os.mkdir(path)
            return path
        except FileExistsError:
            continue  # Try another random name


def remove_all_temp_directories() -> None:
    """
    Removes all temporary directories.

    Returns:
        None
    """
    for entry in os.listdir(temp_dir):
        path = os.path.join(temp_dir, entry)
        if os.path.isdir(path):
            shutil.rmtree(path)
    msg.print({"msg": "RM_TMPDIR"})

