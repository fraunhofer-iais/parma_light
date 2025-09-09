import copy
from graphlib import CycleError, TopologicalSorter
import intern.dbc as dbc
import intern.helper as h
import intern.msg as msg
import intern.database as db
import component.data as d
import component.node as n


def get_workflow_hash_by_referer(referer: dict) -> str:
    """
    Retrieves the hash of a workflow entry by using a referer.

    Args:
        referer (dict): Must have 'name' and 'version' properties, or a 'hash' property, but NOT both.

    Returns:
        str: The hash of the workflow entry object.

    Raises:
        Raises an error if the workflow entry is not found.
    """
    if "name" in referer and "version" in referer and not "hash" in referer:
        hash = h.opt_hash_by_key_value_and_version(db._workflow, referer["name"], referer["version"])
        dbc.assert_true(hash, {"msg": "NOT_FOUND", "kind": "workflow definition", "name": referer["name"]})
        return hash
    elif not "name" in referer and not "version" in referer and "hash" in referer:
        return db.get_hash_from_prefix(referer["hash"], table= db._workflow)
    dbc.raise_error({"msg": "NOT_FOUND", "kind": "workflow", "name": msg.referer2str(referer)})

def get_workflow_by_hash(hash: str) -> dict:
    """
    Retrieves a workflow entry by its hash.

    Args:
        hash (str): The hash of the workflow entry.

    Returns:
        dict: The workflow entry object.

    Raises:
        Raises an error if the workflow entry is not found.
    """
    workflow = db._workflow[hash]
    dbc.assert_true(
        workflow, {"msg": "NOT_FOUND", "kind": "workflow: hash", "name": hash}
    )
    return workflow

def add_workflow(workflow: dict, logged_in_user: str) -> str:
    """
    Adds a new workflow entry to the database after validating its structure and channels.

    Args:
        workflow (dict): The workflow entry object.
        logged_in_user (str): The user performing the operation.

    Returns:
        str: The hash of the added workflow entry.
    """
    h.validate_user_input(workflow, "workflow_def")
    h.all_keys_different(
        [workflow["input"].keys(),
         workflow["output"].keys(),
         workflow["bind"].keys(),
         workflow["connect"].keys()
        ]
    )
    for node in workflow["nodes"].values():
        if "node" in node:
            node_usage = node["node"]
            hash_of_node_def = n.get_node_hash_by_referer(node_usage)
            node["_hash_of_node_def"] = hash_of_node_def
            node_def = n.get_node_by_hash(hash_of_node_def)
            _validate_node_def_matches_node_use("node", node_usage, node_def, node)
            _validate_renamings("node", node_usage, node["input"], [workflow["input"], workflow["bind"], workflow["connect"]])
            _validate_renamings("node", node_usage, node["output"], [workflow["output"], workflow["connect"]])
        elif "workflow" in node:
            workflow_usage = node["workflow"]
            hash_of_workflow_def = get_workflow_hash_by_referer(workflow_usage)
            node["_hash_of_workflow_def"] = hash_of_workflow_def
            workflow_def = get_workflow_by_hash(hash_of_workflow_def)
            _validate_node_def_matches_node_use("sub workflow", workflow_usage, workflow_def, node)
            _validate_renamings("sub workflow", workflow_usage, node["input"], [workflow["input"], workflow["bind"], workflow["connect"]])
            _validate_renamings("sub workflow", workflow_usage, node["output"], [workflow["output"], workflow["connect"]]) 
    all_renamings = set(
            renaming
            for node in workflow["nodes"].values()
            for renaming in list(node["input"].values()) + list(node["output"].values())
        )
    _validate_wf_channel_used(workflow["input"].keys(), all_renamings)
    _validate_wf_channel_used(workflow["output"].keys(), all_renamings)
    _validate_wf_channel_used(workflow["bind"].keys(), all_renamings)
    _validate_wf_channel_used(workflow["connect"].keys(), all_renamings)
    _validate_full_channel_def(workflow["output"].values())
    _validate_full_channel_def(workflow["connect"].values())
    # _modify_workflow_if_it_is_based_on_another_workflow(workflow)
    input_output_connections = _validate_graph(workflow)
    topological_order = _sort_graph(input_output_connections, workflow)
    if len(topological_order) <= 0:
        dbc.assert_true(
            len(workflow["nodes"]) == 1,
            { "msg": "INVALID_WORKFLOW", "reason": "inconsistency in topological sorting" },
            user_error=False
        )
        topological_order = list( workflow["nodes"].keys() ) # must be a singleton
    else:
        topological_order = topological_order[::-1]

    workflow["_topological_order"] = topological_order
    
    h.check_that_node_channels_are_bound(workflow["nodes"], n.get_node_by_hash, get_workflow_by_hash)

    return db.enrich_and_store_in_table(db._workflow, workflow, logged_in_user)

def refine_workflow(refinement: dict, logged_in_user: str) -> str:
    """
    Takes an existing workflow and replaces nodes and replaces bind channels
    to obtain a slightly modified workflow.

    Args:
        refinement (dict): The definition, what in which workflow should be refined.
        logged_in_user (str): The user performing the operation.

    Returns:
        str: The hash of the new workflow entry.
    """
    h.validate_user_input( refinement, "refine_def")
    hash_of_workflow = get_workflow_hash_by_referer(refinement["workflow"])
    workflow_to_be_refined = db._workflow[hash_of_workflow]
    workflow = copy.deepcopy(workflow_to_be_refined)
    workflow_to_be_refined = {}
    workflow["name"] = refinement["name"]
    for key in list(workflow.keys()):
        if key and key[0] == "_":
           del workflow[key]
    for node_def in workflow["nodes"].values():
        node_def.pop("_hash_of_node_def", None)
        node_def.pop("_hash_of_workflow_def", None)
    if "replace_by_node" in refinement:
        for node_name, replacement_def in refinement["replace_by_node"].items():
            the_replacing_node = n.get_node_by_hash(n.get_node_hash_by_referer(replacement_def))
            _make_node_replacement("node", workflow, node_name, replacement_def, the_replacing_node)
    if "replace_by_workflow" in refinement:
        for node_name, replacement_def in refinement["replace_by_workflow"].items():
            the_replacing_node = get_workflow_by_hash(get_workflow_hash_by_referer(replacement_def))
            _make_node_replacement("workflow", workflow, node_name, replacement_def, the_replacing_node)
    if "replace_bind" in refinement:
        bind_section = workflow["bind"]
        for channel_name, replacement_def in refinement["replace_bind"].items():
            if channel_name in bind_section:
                channel_def_to_be_replaced = bind_section[channel_name]
                type_ok = channel_def_to_be_replaced["type"] == replacement_def["type"]
                format_ok = channel_def_to_be_replaced["format"] == replacement_def["format"]
                dbc.assert_true(type_ok and format_ok, {"msg": "REFINE_MISMATCH"})
                bind_section[channel_name] = replacement_def
            else:
                dbc.raise_error({"msg": "REFINE_MISMATCH"})
    return add_workflow(workflow, logged_in_user)


def _make_node_replacement(
    what_should_be_replaced: str,
    workflow: dict,
    node_name: str,
    replacement_def: dict,
    the_replacing_node: dict
) -> None:
    """
    Replaces a node or workflow in the workflow definition.

    Args:
        what_should_be_replaced (str): "node" or "workflow".
        workflow (dict): The workflow object.
        node_name (str): The name of the node to replace.
        replacement_def (dict): The replacement definition.
        the_replacing_node (dict): The replacing node definition.

    Returns:
        None
    """
    node_def_to_be_replaced = workflow["nodes"][node_name]
    inputs_ok = the_replacing_node["input"].keys() == node_def_to_be_replaced["input"].keys()
    outputs_ok = the_replacing_node["output"].keys() == node_def_to_be_replaced["output"].keys()
    dbc.assert_true(inputs_ok and outputs_ok, {"msg": "REFINE_MISMATCH"})
    node_def_to_be_replaced.pop("node", None)
    node_def_to_be_replaced.pop("workflow", None)
    node_def_to_be_replaced[what_should_be_replaced] = replacement_def


def _validate_wf_channel_used(workflow_channels, all_renamings) -> None:
    """
    Validates that each workflow channel is used in the workflow.

    Args:
        workflow_channels (iterable): The workflow channel names.
        all_renamings (set): Set of all used channel renamings.

    Raises:
        Raises an error if a workflow channel is unused.
    """
    for workflow_channel in workflow_channels:
        if not workflow_channel in all_renamings:
            dbc.raise_error({"msg": "WORKFLOW_CHANNEL_UNUSED", "channel_name": workflow_channel})
    return


def _validate_node_def_matches_node_use(
    node_or_workflow_str: str,
    node_or_workflow_name,
    node_def: dict,
    node_usage: dict
) -> None:
    """
    Checks that the node or workflow usage matches its definition in terms of input/output channels.

    Args:
        node_or_workflow_str (str): "node" or "sub workflow".
        node_or_workflow_name: The name or referer of the node or workflow.
        node_def (dict): The node or workflow definition.
        node_usage (dict): The node or workflow usage.

    Raises:
        Raises an error if the usage does not match the definition.
    """
    if _keys_found_in_other_keys(node_usage["input"].keys(), node_def["input"].keys()):
        if _keys_found_in_other_keys(node_usage["output"].keys(), node_def["output"].keys()):
            return
    referer_name = msg.referer2str(node_or_workflow_name)
    dbc.raise_error(
            {"msg": "NODE_DEF_AND_USE_MISMATCH",
             "node_type": node_or_workflow_str,
             "referer_name": referer_name})


def _validate_full_channel_def(defs) -> None:
    """
    Validates that all channel definitions are complete.

    Args:
        defs (iterable): Iterable of channel definitions.

    Raises:
        Raises an error if a channel definition is invalid.
    """
    error = False
    for a_def in defs:
        if a_def["type"] == "directory":
            if not "storage" in a_def or not "hash" in a_def or not "user_path" in a_def:
                error = True
                break
        elif a_def["type"] == "file":
            if "storage" in a_def or "hash" in a_def or "user_path" in a_def:
                error = True
                break
    if error:
        dbc.raise_error({"msg": "INVALID_CHANNEL_DEF"})


def _keys_found_in_other_keys(keys1, keys2) -> bool:
    """
    Checks if all keys in keys1 are present in keys2.

    Args:
        keys1 (iterable): Keys to check.
        keys2 (iterable): Keys to check against.

    Returns:
        bool: True if all keys in keys1 are in keys2, False otherwise.
    """
    for key in keys1:
        if not key in keys2:
            return False
    return True


def _validate_renamings(
    node_or_workflow_str: str,
    node_or_workflow_name,
    channels_of_used_node: dict,
    array_of_legal_channel_groups_of_workflow: list
) -> None:
    """
    Validates that all channels used by a node or workflow are present in a legal channel groups.

    Args:
        node_or_workflow_str (str): "node" or "sub workflow".
        node_or_workflow_name: The name or referer of the node or workflow.
        channels_of_used_node (dict): Channels used by the node or workflow.
        array_of_legal_channel_groups_of_workflow (list): List of legal channel groups.

    Raises:
        Raises an error if a channel is missing.
    """
    for channel_in_workflow_name in channels_of_used_node.values():
        found = False
        for legal_channel_group in array_of_legal_channel_groups_of_workflow:
            if channel_in_workflow_name in legal_channel_group:
                found = True
                break
        if not found:
            referer_name = msg.referer2str(node_or_workflow_name)
            dbc.raise_error(
                {"msg": "NODE_CHANNEL_MISSING_IN_WF_CHANNELS",
                "node_type": node_or_workflow_str,
                "referer_name": referer_name,
                "channel_name": channel_in_workflow_name})
    return


def _is_list_of_strings(variable) -> bool:
    """
    Checks if the variable is a non-empty list of strings.

    Args:
        variable: The variable to check.

    Returns:
        bool: True if variable is a non-empty list of strings, False otherwise.
    """
    return (
        isinstance(variable, list)
        and len(variable) > 0
        and all(isinstance(item, str) for item in variable)
    )


def _validate_graph(workflow: dict) -> dict:
    """
    Validates the input/output channel connections in the workflow and checks for errors.

    Args:
        workflow (dict): The workflow entry object.

    Returns:
        dict: A dictionary describing input/output connections.

    Raises:
        Raises errors for invalid channel usage.
    """
    inputs = workflow["input"].keys()
    outputs = workflow["output"].keys()
    binds = workflow["bind"].keys()

    input_output_connections = {}
    for node_name, node in workflow["nodes"].items():
        for channel in node["input"].values():
            if channel not in input_output_connections:
                input_output_connections[channel] = {
                "output": set(),
                "input": set(),
            }
            input_output_connections[channel]["input"].add(node_name)
        for channel in node["output"].values():
            if channel not in input_output_connections:
                input_output_connections[channel] = {
                "output": set(),
                "input": set(),
            }
            input_output_connections[channel]["output"].add(node_name)
    for channel_name, connected_nodes in input_output_connections.items():
        nodes_reading = connected_nodes["input"]
        nodes_writing = connected_nodes["output"]
        if len(nodes_reading) == 0 and not channel_name in outputs:
            dbc.raise_error({"msg": "INVALID_WORKFLOW", f"reason": "channel \"{channel_name}\" not read"})
        if len(nodes_writing) > 1:
            dbc.raise_error({"msg": "INVALID_WORKFLOW", "reason": f"channel \"{channel_name}\" written more than once"})
        if len(nodes_writing) > 0 and (channel_name in inputs or channel_name in binds):
            dbc.raise_error({"msg": "INVALID_WORKFLOW", "reason": f"channel \"{channel_name}\" forbidden to write"})
    return input_output_connections


def _sort_graph(input_outputs: dict, workflow: dict) -> list:
    """
    Sorts the graph of input-output connections in topological order.

    Args:
        input_outputs (dict): The input-output channels of the graph.
        workflow (dict): The workflow entry object.

    Returns:
        list: The topological order of the graph.

    Raises:
        Raises an error if a cycle is detected.
    """
    graph = {}
    for channel in input_outputs.values():
        if len(channel["output"]) == 0:
            pass # never written, thus no need for sequential run
        elif len(channel["output"]) > 1:
            dbc.raise_error({"msg": "INVALID_WORKFLOW", "reason": "channel written more than once"})
        else:
            output = next(iter(channel["output"]))
            if output not in graph:
                graph[output] = set()
            graph[output].update(channel["input"])
    if "sequence" in workflow:
        dbc.assert_true(
            isinstance(workflow["sequence"], list),
            {"msg": "INVALID_WORKFLOW", "reason": "sequence no list"},
        )
        for sequence in workflow["sequence"]:
            dbc.assert_true(
                _is_list_of_strings(sequence),
                {"msg": "INVALID_WORKFLOW", "reason": "sequence no list of node names"},
            )
            dbc.assert_true(
                all(node in workflow["nodes"] for node in sequence),
                {"msg": "INVALID_WORKFLOW", "reason": "node in sequence unknown"},
            )
            before = sequence[0]
            after = sequence[1:]
            if before not in graph:
                graph[before] = set(after)
            else:
                graph[before].update(after)

    try:
        ts = TopologicalSorter(graph)
        return list(ts.static_order())
    except CycleError:
        dbc.raise_error(
            {"msg": "INVALID_WORKFLOW", "reason": "cycle in operators in workflow"}
        )
