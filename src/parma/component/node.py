import intern.dbc as dbc
import intern.helper as h
import intern.database as db


def get_node_hash_by_referer(referer: dict) -> str:
    """
    Retrieves the hash of a node entry by using a referer.

    Args:
        referer (dict): Must have 'name' and 'version' properties, or a 'hash' property, but NOT both.

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
    h.validate_user_input(node, "node_def")
    h.all_keys_different([node["input"].keys(), node["output"].keys()])

    image_id = h.get_docker_image_digest(node["image"])
    dbc.assert_true(
        image_id, {"msg": "NOT_FOUND", "kind": "image", "name": node["image"]}
    )
    node["_image_id"] = image_id

    return db.enrich_and_store_in_table(db._node, node, logged_in_user)
