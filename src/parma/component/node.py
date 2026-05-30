import os
import stat
import subprocess
import intern.dbc as dbc
import intern.helper as h
import intern.database as db
import component.data as d


CONSTANT_TYPES = ("str", "int", "float", "bool", "json")
# all types a channel (of a node) or a bind (of a workflow) may have
CHANNEL_TYPES = ("file", "directory", "environment_var") + CONSTANT_TYPES


def validate_channel_types(channels, what: str = "channel") -> None:
    """
    Checks, that every channel (or bind) of a dict name -> definition has a known "type". Done before the schema
    validation, because for an unknown type the schema reports a misleading error (e.g. a missing "format").

    Args:
        channels: dict name -> channel definition. Anything else is ignored (the schema reports it).
        what (str): "channel" or "bind", used in the error message.

    Raises:
        Raises an error naming the channel, the unknown type and the allowed types.
    """
    if not isinstance(channels, dict):
        return
    for name, channel in channels.items():
        if not isinstance(channel, dict) or "type" not in channel:
            continue
        channel_type = channel["type"]
        dbc.assert_true(
            channel_type in CHANNEL_TYPES,
            {"msg": "INVALID_CHANNEL_USE", "name": name,
             "reason": f"unknown {what} type \"{channel_type}\", allowed are: {', '.join(CHANNEL_TYPES)}"}
        )
"""Channel types whose value is a constant (passed as environment variable or command line parameter)."""


def get_node_hash_by_referer(referer: dict) -> str:
    """
    Retrieves the hash of a node entry by using a referer.

    Args:
        referer (dict): Must have 'name' and 'version' properties, or a 'hash' property, but NOT both.
                A hash is for internal use only (e.g. by the frontend, hashes from lists); user inputs
                (definitions, referer files) are validated against the schema "name_version" before.

    Returns:
        str: The hash of the node entry object.

    Raises:
        Raises an error if the node entry is not found.
    """
    if "name" in referer and "version" in referer and not "hash" in referer:
        hash = h.opt_hash_by_key_value_and_version(db._node, referer["name"], referer["version"])
        dbc.assert_true(hash, {"msg": "NOT_FOUND", "kind": "node definition", "name": referer["name"]})
        return hash
    elif not "name" in referer and not "version" in referer and "hash" in referer and referer["hash"] in db._node:
        return referer["hash"]
    dbc.raise_error({"msg": "NOT_FOUND", "kind": "node definition", "name": referer.get("name", referer.get("hash", ""))})


def get_all_nodes() -> list:
    """
    Returns a list of all node entries known to the backend, each entry
    including its hash under the key '_hash'.

    Returns:
        list[dict]: All node objects.
    """
    return [dict(node, _hash=hash) for hash, node in db._node.items()]


def delete_node(hash: str, logged_in_user: str) -> None:
    """
    Deletes a node entry from the database by its hash.

    Args:
        hash (str): The hash of the node entry to delete.
        logged_in_user (str): The user performing the operation.

    Raises:
        Raises an error if the node entry is not found.
    """
    dbc.assert_true(hash in db._node, {"msg": "NOT_FOUND", "kind": "node definition", "name": hash})
    del db._node[hash]


def get_node_by_hash(hash: str) -> dict:
    """
    Retrieves a node entry by its hash.

    Args:
        hash (str): The hash of the node entry.

    Returns:
        dict: The node entry object.

    Raises:
        Raises an error if the node entry is not found.
    """
    node = db._node.get(hash)
    dbc.assert_true(
        node, {"msg": "NOT_FOUND", "kind": "node definition", "name": hash}
    )
    return node


def add_node(node: dict, logged_in_user: str) -> str:
    """
    Adds a new node entry to the database.

    Args:
        node (dict): Node details.
        logged_in_user (str): The user performing the operation.

    Returns:
        str: The hash of the added node entry.
    """
    _normalize_channel_lists(node)
    validate_channel_types(node.get("input"))
    validate_channel_types(node.get("output"))
    _default_format_of_constants(node)
    h.validate_user_input(node, "node_def")
    h.all_keys_different([node["input"].keys(), node["output"].keys()])
    _validate_value_channels(node)

    if "image" in node:
        image_id = h.get_docker_image_digest(node["image"])
        dbc.assert_true(
            image_id, {"msg": "NOT_FOUND", "kind": "image", "name": node["image"]}
        )
        _validate_channel(node["input"], "path_in_container")
        _validate_channel(node["output"], "path_in_container")
        node["_image_id"] = image_id
    elif "bash" in node:
        if h.WINDOWS:
            details = "bash nodes are not supported on windows"
            dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
        bash_id = d.get_data_hash_by_referer(node["bash"])
        _validate_channel(node["input"], "environment_var_in_container")
        _validate_channel(node["output"], "environment_var_in_container")
        path_to_bash_script = d.get_path_by_hash(bash_id)
        h.set_file_executable(path_to_bash_script) # TODO: better solution required. Works on linux only
        node["_bash_id"] = bash_id
    elif "nix" in node:
        if h.WINDOWS:
            details = "nix nodes are not supported on windows"
            dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
        _validate_channel(node["input"], "environment_var_in_container")
        _validate_channel(node["output"], "environment_var_in_container")
        for channel_name, channel in node["input"].items():
            dbc.assert_true(
                "command_line_parameter" not in channel,
                {"msg": "INVALID_CHANNEL_USE", "name": channel_name, "reason": "command line parameters are not supported for nix nodes"}
            )
        # TODO: run the nix script to get the nix hash and store it as metadata to achieve reproducability
    else:
        details = "node is neither image nor bash"
        dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)

    return db.enrich_and_store_in_table(db._node, node, logged_in_user)


def _validate_channel(channel_dict, key):
    for channel_name, channel in channel_dict.items():
        channel_type = channel["type"]
        if channel_type == "file" or channel_type == "directory":
            dbc.assert_true(
                key in channel, {"msg": "NOT_FOUND", "kind": f"{key} in channel", "name": channel_name}
            )

def _normalize_channel_lists(node: dict) -> None:
    """
    Accepts the list format of channels ("inputs"/"outputs": [{"name": ..., ...}, ...]) and converts it
    in place to the dict format ("input"/"output": {name: {...}, ...}) used internally.
    A node must not use both formats for the same direction.
    """
    for list_key, dict_key in (("inputs", "input"), ("outputs", "output")):
        if list_key not in node:
            continue
        channel_list = node.pop(list_key)
        dbc.assert_true(
            dict_key not in node,
            {"msg": "VALIDATION_ERROR", "definition_of": "node_def", "error": f"both \"{list_key}\" and \"{dict_key}\" given"}
        )
        dbc.assert_true(
            isinstance(channel_list, list),
            {"msg": "VALIDATION_ERROR", "definition_of": "node_def", "error": f"\"{list_key}\" must be a list"}
        )
        channel_dict = {}
        for channel in channel_list:
            dbc.assert_true(
                isinstance(channel, dict) and isinstance(channel.get("name"), str),
                {"msg": "VALIDATION_ERROR", "definition_of": "node_def", "error": f"each entry of \"{list_key}\" needs a \"name\""}
            )
            channel = dict(channel)
            name = channel.pop("name")
            dbc.assert_true(name not in channel_dict, {"msg": "DUPLICATE_CHANNEL", "name": name})
            channel_dict[name] = channel
        node[dict_key] = channel_dict


def _default_format_of_constants(node: dict) -> None:
    """
    For inputs of a constant type (str, int, float, bool, json) the format is optional: it defaults to "str".
    """
    for channel in (node.get("input") or {}).values():
        if isinstance(channel, dict) and channel.get("type") in CONSTANT_TYPES:
            channel.setdefault("format", "str")


def _validate_value_channels(node: dict) -> None:
    """
    Constants (types str, int, float, bool, json) and environment vars are passed as environment variable
    or as command line parameter, never as a path. Command line parameters are allowed for inputs only.
    Outputs must not have a constant type.
    """
    for channel_name, channel in node["input"].items():
        channel_type = channel["type"]
        if "command_line_parameter" in channel:
            dbc.assert_true(
                channel_type in CONSTANT_TYPES or channel_type == "environment_var",
                {"msg": "INVALID_CHANNEL_USE", "name": channel_name, "reason": f"type \"{channel_type}\" can't be passed as command line parameter"}
            )
        if channel_type in CONSTANT_TYPES or channel_type == "environment_var":
            dbc.assert_true(
                "path_in_container" not in channel,
                {"msg": "INVALID_CHANNEL_USE", "name": channel_name, "reason": f"type \"{channel_type}\" can't be passed by path"}
            )
    for channel_name, channel in node["output"].items():
        dbc.assert_true(
            "command_line_parameter" not in channel,
            {"msg": "INVALID_CHANNEL_USE", "name": channel_name, "reason": "command line parameters are allowed for inputs only"}
        )
        dbc.assert_true(
            channel["type"] not in CONSTANT_TYPES,
            {"msg": "INVALID_CHANNEL_USE", "name": channel_name, "reason": f"output of type \"{channel['type']}\" is not supported"}
        )
