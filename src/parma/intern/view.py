import json
import os
import re
import shutil
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

import intern.dbc as dbc
import intern.database as db
import intern.msg as msg
import intern.helper as h
import component.data as d
import component.run as r
import component.workflow as wf


def datastore_export(param: Dict[str, Any]) -> None:
    """
    Copies a file to a destination.

    Args:
        param (dict): Defines what to export. Must contain a referer and a "to" key for the target file.

    Returns:
        None
    """
    hash = d.get_data_hash_by_referer(param)
    data = d.get_data_by_hash(hash)
    name = data["name"]
    version = data["_version"]
    user_path = data.get("user_path", "---")
    print(f"name: {name} version: {version} hash: {db.shrink_hash(hash)}, path: {user_path}")
    path = d.get_path_by_hash(hash)
    dbc.assert_true("to" in param, {"msg": "INVALID_CMD"})
    target_file = param["to"]
    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    shutil.copyfile(path, target_file)


def get_data(param: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns file content in property "content".

    Args:
        param (dict): Describes the file to return.

    Returns:
        dict: Contains success, name, version, hash, and content.
    """
    hash = d.get_data_hash_by_referer(param)
    data = d.get_data_by_hash(hash)
    
    path = data["_path"]
    store_in_platform = data["storage"] == "platform"
    use_content_hash = data["hash"] == "true"

    if store_in_platform:
        path = os.path.join(db.data_dir, path)
    if use_content_hash and not store_in_platform:
        hash_of_content = h.make_git_like_hash_of_a_file(path)
        dbc.assert_true(hash_of_content == data["_hash_of_content"], {"msg": "HASH_MISMATCH", "path": path})
    else:
        pass # we assume, that files stored in the platform are not modified

    dbc.assert_true(path and os.path.isfile(path), {"msg": "NO_FILE_OR_NOT_FOUND", "name": path})
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"success": True, "name": data["name"], "version": data["_version"], "hash": db.shrink_hash(hash), "content": content}


def export(param: Dict[str, Any]) -> None:
    """
    Copies file content into file system. Only works for files.

    Args:
        param (dict): Describes the file to return. Must contain a referer and a "to" key for the target file.

    Returns:
        None
    """
    dbc.assert_true("to" in param, {"msg": "INVALID_COMMAND"})
    target_file = param["to"]
    hash = d.get_data_hash_by_referer(param)
    data = d.get_data_by_hash(hash)
    user_path = data.get("user_path", "---")
    dbc.assert_true(user_path and os.path.isfile(user_path), {"msg": "NO_FILE_OR_NOT_FOUND", "name": user_path})
    os.makedirs(os.path.dirname(target_file), exist_ok=True)
    shutil.copyfile(user_path, target_file)


def get_name_version_and_hash_and_entity_of_workflow_or_run_by_referer(
    referer: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Retrieves a workflow or run entity by referer.

    Args:
        referer (dict): The referer object (may contain "name", "version", or "hash").

    Returns:
        tuple: (name_version__and_hash, entity) for the workflow or run.

    Raises:
        Raises an error if neither workflow nor run is found.
    """
    try:
        hash = wf.get_workflow_hash_by_referer(referer)
        entity = wf.get_workflow_by_hash(hash)
    except Exception:
        try:
            hash = r.get_run_hash_by_referer(referer)
            entity = r.get_run_by_hash(hash)
        except Exception:
            dbc.raise_error({"msg": "NOT_FOUND", "kind": "workflow or run", "name": msg.referer2str(referer)})

    name_version__and_hash = {"name": entity["name"], "_version": entity["_version"], "hash": db.shrink_hash(hash)}
    return (name_version__and_hash, entity)


def view_table(param: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retrieves a list of data items from the rows of a table for later formatting.
    Here the columns are defined, that will be shown.

    Args:
        param (dict): Optional parameters for table name, filtering and formatting.
            Must contain "name" (table/entity: "user", "data", "node", "workflow", "run").

    Returns:
        dict: Contains a 2D list representing the table under the "table" key.
    """
    table_name = param.get("name", "run")
    if table_name == "user":
        keys_to_report = ["name", "display_name", "su"]
        dict_to_report = db._user
    elif table_name == "data":
        keys_to_report = [("_HASH_", db.shrink_hash), "name", "_version", "type", "storage", "hash", "user_path", ("_hash_of_content", db.shrink_hash)]
        dict_to_report = db._data
    elif table_name == "node":
        keys_to_report = ["name", "_version", ("image", _image_name), "input", "output"]
        dict_to_report = db._node
    elif table_name == "workflow":
        keys_to_report = [("_HASH_", db.shrink_hash), "name", "_version", "input", "output", "_topological_order"]
        dict_to_report = db._workflow
    elif table_name == "run":
        keys_to_report = [("_HASH_", db.shrink_hash), "name", "_version", "_success", "_topological_order"]
        dict_to_report = db._run
    return _make_table(dict_to_report.items(), keys_to_report, param)


def _make_table(
    dict_items_to_report: Iterable[Tuple[Any, dict]],
    keys_to_report: List[Union[str, Tuple[str, Callable[[Any], Any]]]],
    print_params: Dict[str, Any]
) -> Dict[str, List[List[Any]]]:
    """
    Retrieves a list of data items from the rows of a table for later formatting.

    Args:
        dict_items_to_report (iterable): Items (key, value) to include in the table.
        keys_to_report (list): Keys or (key, formatter) tuples to include as columns.
        print_params (dict): Optional parameters for filtering (pattern, limit).

    Returns:
        dict: Contains a 2D list representing the table under the "table" key.
    """
    pattern: Optional[re.Pattern] = None

    if print_params.get("pattern"):
        pattern = re.compile(print_params["pattern"])

    keys_to_print: List[str] = []
    for key in keys_to_report:
        if type(key) == tuple:
            key = key[0]
        key = key.lower()
        key = key[1:] if key.startswith("_") else key
        keys_to_print.append(key)

    unsorted_table: Dict[Any, List[Any]] = {}
    for item_key, item_value in dict_items_to_report:
        if pattern:
            print_representation = json.dumps(item_value)
            if not pattern.search(print_representation):
                continue
        row: List[Any] = []
        for key in keys_to_report:
            if type(key) == tuple:
                formatter = key[1]
                key = key[0]
            else:
                formatter = None
            if key == "_HASH_":
                column = item_key if formatter is None else formatter(item_key)
                row.append(column)
            elif key in item_value:
                column = item_value[key]
                if formatter is None:
                    if type(column) == dict:
                        row.append(str(list(column.keys())))
                    else:
                        row.append(str(column))
                else:
                    row.append(formatter(column))
            else:
                row.append("")
        unsorted_table[item_value["_date"]] = row

    limit: Optional[int] = None
    if print_params.get("limit"):
        limit = int(print_params["limit"])
    counter: int = 0
    sorted_keys: List[Any] = sorted(unsorted_table.keys(), reverse=True)
    table: List[List[Any]] = [keys_to_print]
    for sorted_key in sorted_keys:
        if limit and counter >= limit:
            break
        counter += 1
        table.append(unsorted_table[sorted_key])
    return {"table": table}


def _image_name(image: dict) -> str:
    """
    Returns a string representation of an image's name and version.

    Args:
        image (dict): The image dictionary.

    Returns:
        str: The formatted image name and version.
    """
    return f'{image.get("name","---")}:{image.get("version","---")}'


