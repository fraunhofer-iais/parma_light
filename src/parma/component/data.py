import hashlib
import os
import random
import re
import shutil
import intern.dbc as dbc
import intern.helper as h
import intern.database as db
import intern.view as v
import intern.msg as msg


def get_data_hash_by_referer(referer: dict) -> str:
    """
    Retrieves the hash of a data entry by using a referer.

    Args:
        referer (dict): Must have 'name' and 'version' properties, or a 'hash' property, but NOT both.

    Returns:
        str: The hash of the data entry object.

    Raises:
        Raises an error if the data entry is not found.
    """
    if "name" in referer and "version" in referer and not "hash" in referer:
        hash = h.opt_hash_by_key_value_and_version(db._data, referer["name"], referer["version"])
        dbc.assert_true(hash, {"msg": "NOT_FOUND", "kind": "data definition", "name": referer["name"]})
        return hash
    elif not "name" in referer and not "version" in referer and "hash" in referer:
        hash = h.opt_hash_by_shrinked_hash(db._data, referer["hash"])
        dbc.assert_true(hash, {"msg": "NOT_FOUND", "kind": "data definition", "name": referer["hash"]})
        return hash
    dbc.raise_error({"msg": "NOT_FOUND", "kind": "data definition", "name": msg.referer2str(referer)})


def get_data_by_hash(hash: str) -> dict:
    """
    Retrieves a data entry by its hash.

    Args:
        hash (str): The hash of the data entry.

    Returns:
        dict: The data entry object.

    Raises:
        Raises an error if the data entry is not found.
    """
    if hash in db._data:
        data = db._data[hash]
        return data
    else:
        dbc.raise_error(
            {"msg": "NOT_FOUND", "kind": "data definition", "name": hash}
        )


def get_data_info_from_workflow_or_run(workflow_or_run: dict) -> list[list]:
    """
    Retrieves detailed data information from a workflow or run.

    Args:
        workflow_or_run (dict): The entity whose data references should be generated.

    Returns:
        list[list]: A 2D array (list of lists) containing data information in tabular format.
    """
    data_array = [["hash", "name in data table", "version", "data ..."]]
    for node_name, node in workflow_or_run["nodes"].items():
        for channel_name, channel in node["input"].items():
            if "_data_hash" in channel:
                _append_data(data_array, f'input to channel "{channel_name}" of node "{node_name}"', channel["_data_hash"])
        for channel_name, channel in node["output"].items():
            if type(channel) == str:
                if "_channel_bindings" in workflow_or_run:
                    channel_bindings = workflow_or_run["_channel_bindings"]
                    if channel in channel_bindings:
                        data_hash = channel_bindings[channel]
                        _append_data(data_array, f'output of channel "{channel_name}" of node "{node_name}"', data_hash)
        
    return data_array


def get_path_by_hash(hash: str, for_mounting= False) -> str:
    """
    Retrieves the file path of a data entry by the hash of the data entry. There is a special case if Parma_light
    is running in a container in DOOD mode. The path is resolved by the demon running on the host, thus for
    mounting the path ON THE HOST that corresponds to the mounted directory is returned

    Args:
        hash (str): The hash of the data entry.

    Returns:
        str: The file path of the data entry.

    Raises:
        Raises an error if the file does not exist.
    """
    data = get_data_by_hash(hash)
    path = data["_path"]

    if data["storage"] == "extern":
        if h.RUNNING_IN_CONTAINER:
            dbc.raise_error( {"msg": "SYSTEM_ERROR", "details": "extern storage not supported with docker"}, user_error=True )
        if os.path.exists(path):
            return path
    else:
        data_path = os.path.join(db.data_dir,path)
        if os.path.exists(data_path):
            if h.RUNNING_IN_CONTAINER and for_mounting:
                return f"{db.data_dir_for_mount}/{path}" # TODO: the slash should be replaced
            else:
                return data_path
    dbc.raise_error({"msg": "NOT_FOUND", "kind": "data definition", "name": hash})


def add_data(
    data: dict,
    logged_in_user: str,
    ignore_errors: bool = False,
    delete_user_path: bool = False
) -> str:
    """
    Adds a new data entry to the database.

    Args:
        data (dict): Data details.
        logged_in_user (str): The user performing the operation.
        ignore_errors (bool): If True, ignore file errors.
        delete_user_path (bool): If True, remove '_user_path' from data after storing.

    Returns:
        str: The hash of the stored data entry.
    """
    h.validate_user_input(data, "data_def")

    user_path = data["user_path"]
    if _is_absolute_path(user_path):
        user_path = os.path.abspath(user_path)
    else:
        user_path = os.path.join(db.base_dir, user_path)

    store_in_platform = data["storage"] == "platform"
    use_content_hash = data["hash"] == "true"

    if data["type"] == "directory":
        dbc.assert_true(not store_in_platform and not use_content_hash,
                        {"msg":"DIRECTORY_RESTRICTION", "path": user_path})
    if use_content_hash:
        hash_of_content = h.make_git_like_hash_of_a_file(user_path)
        data["_hash_of_content"] = hash_of_content
    else:
        hash_of_content = _random_sha1()
    if store_in_platform:
        _store_file(db.data_dir, hash_of_content, user_path, ignore_errors=ignore_errors)
        internal_path_to_file = hash_of_content
    else:
        internal_path_to_file = user_path
    if delete_user_path:
        data.pop("_user_path", None)
    data["_path"] = internal_path_to_file
    return db.enrich_and_store_in_table(db._data, data, logged_in_user)


def _random_sha1() -> str:
    """
    Generates a random SHA-1 hash.

    Returns:
        str: A random SHA-1 hash string.
    """
    random_bytes = random.randbytes(32)
    return hashlib.sha1(random_bytes).hexdigest()


def _store_file(
    target_dir: str,
    content_hash: str,
    source_path: str,
    ignore_errors: bool
) -> None:
    """
    Stores a file in the destination directory using its hash as the filename.

    Args:
        target_dir (str): Directory to store the file into.
        content_hash (str): The hash of the content, used as filename.
        source_path (str): The path to the file to be stored in the platform.
        ignore_errors (bool): If True, ignore file errors.

    Returns:
        None
    """
    try:
        if not _does_file_content_hash_exist(content_hash):
            dest_path = os.path.join(target_dir, content_hash)
            shutil.copy2(source_path, dest_path)
            h.set_file_readonly(dest_path)
    except (OSError, IOError) as e:
        if ignore_errors:
            pass
        else:
            dbc.raise_error({"msg": "NOT_FOUND", "kind": "file", "name": content_hash})


def _does_file_content_hash_exist(hash: str) -> bool:
    """
    Checks if a file content hash exists in the database.

    Args:
        hash (str): The hash of the file content.

    Returns:
        bool: True if the hash exists, False otherwise.
    """
    path_to_content = os.path.join(db.data_dir, hash)
    return os.path.exists(path_to_content)


def _is_absolute_path(path: str) -> bool:
    """
    Checks if a path is absolute on both Windows and Linux systems.

    Args:
        path (str): The path to check

    Returns:
        bool: True if the path is absolute, False if relative
    """
    # Windows drive letter pattern (C:, D:, etc.)
    if re.match(r'^[a-zA-Z]:', path):
        if db.host_os == 'windows':
            if h.RUNNING_IN_CONTAINER:
                dbc.raise_error( {"msg": "SYSTEM_ERROR", "details": "no absolute pathes when running in a container"}, user_error=True )
            else:
                return True
        else:
            dbc.raise_error( {"msg": "SYSTEM_ERROR", "details": "windows path, but host is not windows"}, user_error=True )
    # Unix-style absolute path
    elif path.startswith('/'):
        if h.RUNNING_IN_CONTAINER:
            if path.startswith('/temp_dir/'):
                return True
            else:
                dbc.raise_error( {"msg": "SYSTEM_ERROR", "details": "no absolute pathes when running in a container"}, user_error=True )
        else:
            if db.host_os == 'windows':
                dbc.raise_error( {"msg": "SYSTEM_ERROR", "details": "linux path, but host is not linux"}, user_error=True )
            else:
                return True
    else:        
        return False


def _append_data(data_array: list, msg: str, data_hash: str) -> None:
    """
    Appends data information to a given data array.

    Args:
        data_array (list): The list to which the data information will be appended.
        msg (str): A message describing the context of the data.
        data_hash (str): The hash of the data to retrieve information for.

    Returns:
        None
    """
    data = get_data_by_hash(data_hash)
    name = data["name"]
    version = data["_version"]
    data_array.append([db.shrink_hash(data_hash), name, version, msg])
