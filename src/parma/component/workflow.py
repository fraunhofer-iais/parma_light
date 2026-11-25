import copy
from graphlib import CycleError, TopologicalSorter
import intern.dbc as dbc
import intern.helper as h
import intern.msg as msg
import intern.database as db
import component.node as n
import component.data as d


def get_workflow_hash_by_referer(referer: dict) -> str:
    """
    Retrieves the hash of a workflow entry by using a referer.

    Args:
        referer (dict): Must have 'name' and 'version' properties, or a 'hash' property, but NOT both.
                A hash is for internal use only (e.g. by the frontend, hashes from lists); user inputs
                (definitions, referer files) are validated against the schema "name_version" before.

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

def get_all_workflows() -> list:
    """
    Returns a list of all workflow entries known to the backend, each entry
    including its hash under the key '_hash'.

    Returns:
        list[dict]: All workflow objects.
    """
    return [dict(workflow, _hash=hash) for hash, workflow in db._workflow.items()]

def delete_workflow(hash: str, logged_in_user: str) -> None:
    """
    Deletes a workflow entry from the database by its hash.

    Args:
        hash (str): The hash of the workflow entry to delete.
        logged_in_user (str): The user performing the operation.

    Raises:
        Raises an error if the workflow entry is not found.
    """
    dbc.assert_true(hash in db._workflow, {"msg": "NOT_FOUND", "kind": "workflow definition", "name": hash})
    del db._workflow[hash]

def add_workflow(workflow: dict, logged_in_user: str) -> str:
    """
    Adds a new workflow entry to the database after validating its structure and channels.

    Args:
        workflow (dict): The workflow entry object.
        logged_in_user (str): The user performing the operation.

    Returns:
        str: The hash of the added workflow entry.
    """
    prepare_workflow(workflow)
    return db.enrich_and_store_in_table(db._workflow, workflow, logged_in_user, hash_function=workflow_hash)


# -- layout and identity of workflows ---------------------------------------------------------------
# The hash of a workflow is its execution identity: the layout of the workflow editor ("litegraph" of
# nodes, inputs, outputs and binds; "pos" of older definitions) isn't part of it. Thus the layout of a
# stored workflow can be changed in place without changing its hash, version and date.
_LAYOUT_KEYS = ("litegraph", "pos")
_LAYOUT_SECTIONS = ("nodes", "input", "output", "bind", "connect")
# metadata of the store and data derived from the workflow: not compared to detect a layout-only change
# (the topological order may differ for the same graph, if the editor lists the nodes in another order)
_METADATA_KEYS = ("_version", "_date", "_hash_of_creating_user", "_topological_order")


def _without_layout(workflow: dict) -> dict:
    """a deep copy of the workflow without the layout of the editor"""
    result = copy.deepcopy(workflow)
    for section in _LAYOUT_SECTIONS:
        for definition in (result.get(section) or {}).values():
            if isinstance(definition, dict):
                for key in _LAYOUT_KEYS:
                    definition.pop(key, None)
    return result


def workflow_hash(workflow: dict) -> str:
    """the hash of a workflow: the hash of its content without the layout of the editor"""
    return h.make_git_like_hash_of_json(_without_layout(workflow))


def _semantics(workflow: dict) -> dict:
    """what a workflow executes: the workflow without layout, metadata of the store and derived data"""
    result = _without_layout(workflow)
    for key in _METADATA_KEYS:
        result.pop(key, None)
    return result


def save_workflow(workflow: dict, base_hash: str, logged_in_user: str) -> tuple:
    """
    Saves a workflow from the workflow editor. If it differs from the stored workflow "base_hash" (the one
    loaded into the editor) only by its layout, the layout of the stored workflow is replaced in place: hash,
    version, date and creating user are unchanged. Otherwise a new workflow entry (a new version) is added.

    Args:
        workflow (dict): The workflow entry object.
        base_hash (str): The hash of the workflow loaded into the editor, None for a new workflow.
        logged_in_user (str): The user performing the operation.

    Returns:
        tuple: (hash of the stored workflow entry, True if only the layout was changed)
    """
    prepare_workflow(workflow)
    stored = db._workflow.get(base_hash) if base_hash else None
    if stored is None or _semantics(workflow) != _semantics(stored):
        return db.enrich_and_store_in_table(db._workflow, workflow, logged_in_user, hash_function=workflow_hash), False
    with db._table_mutex:
        for section in _LAYOUT_SECTIONS:
            new_section = workflow.get(section) or {}
            old_section = stored.get(section) or {}
            for name, definition in old_section.items():
                for key in _LAYOUT_KEYS:
                    definition.pop(key, None)
                    if key in new_section[name]:
                        definition[key] = copy.deepcopy(new_section[name][key])
            # the order of inputs and outputs (the slots of a sub workflow) follows the editor. It isn't
            # part of the hash (the JSON is hashed with sorted keys)
            if section in stored:
                stored[section] = {name: old_section[name] for name in new_section}
    dbc.assert_true(workflow_hash(stored) == base_hash,
                    {"msg": "SYSTEM_ERROR", "details": "the hash of a workflow changed by its layout"}, user_error=False)
    return base_hash, True


def prepare_workflow(workflow: dict) -> None:
    """
    Validates a workflow (structure and channels) and enriches it for storing: default formats of constant
    binds, the hashes of the used node and workflow definitions and the topological order of its nodes.
    The workflow is made canonical, thus a round trip through the workflow editor reproduces it and it is
    reproducible over time:
    - versions of nodes, sub workflows and data are frozen: "latest" becomes the version used now
    - the formats of connect and output channels are the formats of the node outputs writing them

    Args:
        workflow (dict): The workflow entry object. It is modified.
    """
    n.validate_channel_types(workflow.get("bind"), "bind")
    _default_format_of_constant_binds(workflow.get("bind"))
    h.validate_user_input(workflow, "workflow_def")
    h.all_keys_different(
        [workflow["input"].keys(),
         workflow["output"].keys(),
         workflow["bind"].keys(),
         workflow["connect"].keys()
        ]
    )
    for node_name, node in workflow["nodes"].items():
        if "if" in node:
            _validate_if_node(node_name, node, workflow)
        else:
            _validate_used_node(node, workflow)
    _freeze_data_binds(workflow["bind"])
    _normalize_written_formats(workflow)
    all_renamings = set(
            renaming
            for node in workflow["nodes"].values()
            for renaming in node_input_channels(node) + node_output_channels(node)
        )
    _validate_wf_channel_used(workflow["input"].keys(), all_renamings)
    _validate_wf_channel_used(workflow["output"].keys(), all_renamings)
    _validate_wf_channel_used(workflow["bind"].keys(), all_renamings)
    _validate_wf_channel_used(workflow["connect"].keys(), all_renamings)
    _validate_full_channel_def(workflow["output"].values())
    _validate_full_channel_def(workflow["connect"].values())
    _validate_bind_values(workflow["bind"])
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

    h.check_that_node_channels_are_bound(used_nodes(workflow["nodes"]), n.get_node_by_hash, get_workflow_by_hash)


# -- if nodes ---------------------------------------------------------------------------------------
# An if node of a workflow has a channel "if" of type bool and two branches "then" and "else". A branch
# is a node or a sub workflow with its channel renamings (like a normal workflow node). Depending on the
# value of the "if" channel exactly one branch is executed. The branches may read different channels,
# but must write the SAME channels (with equal type and format). The output names of the branches may
# differ. Thus an if node is a function: it reads the "if" channel and the inputs of both branches and
# writes the common output channels.
IF_BRANCHES = ("then", "else")


def node_input_channels(node: dict) -> list:
    """the workflow channels read by a workflow node. An if node reads the "if" channel and the inputs of both branches"""
    if "if" in node:
        return [node["if"]] + [channel for branch in IF_BRANCHES for channel in node[branch]["input"].values()]
    return list(node["input"].values())


def node_output_channels(node: dict) -> list:
    """the workflow channels written by a workflow node. The branches of an if node write the same channels"""
    if "if" in node:
        return list(node["then"]["output"].values())
    return list(node["output"].values())


def used_nodes(nodes: dict) -> dict:
    """the nodes and sub workflows used in the workflow nodes: an if node is replaced by its branches
    (named "<node name>.then" and "<node name>.else")"""
    result = {}
    for node_name, node in nodes.items():
        if "if" in node:
            for branch in IF_BRANCHES:
                result[f"{node_name}.{branch}"] = node[branch]
        else:
            result[node_name] = node
    return result


def _validate_used_node(node: dict, workflow: dict) -> dict:
    """validates a node or sub workflow used in a workflow (a workflow node or a branch of an if node),
    stores the hash of its definition in it and returns its definition"""
    if "node" in node:
        kind, usage = "node", node["node"]
        hash_of_def = n.get_node_hash_by_referer(usage)
        node["_hash_of_node_def"] = hash_of_def
        definition = n.get_node_by_hash(hash_of_def)
    else:
        kind, usage = "sub workflow", node["workflow"]
        hash_of_def = get_workflow_hash_by_referer(usage)
        node["_hash_of_workflow_def"] = hash_of_def
        definition = get_workflow_by_hash(hash_of_def)
    if "name" in usage:
        # freeze the version: "latest" (and numbers) become the version used now, as a string (like the editor writes it)
        usage["version"] = str(definition["_version"])
    _validate_node_def_matches_node_use(kind, usage, definition, node)
    _validate_renamings(kind, usage, node["input"], [workflow["input"], workflow["bind"], workflow["connect"]])
    _validate_renamings(kind, usage, node["output"], [workflow["output"], workflow["connect"]])
    return definition


def _validate_if_node(node_name: str, node: dict, workflow: dict) -> None:
    """validates an if node: the "if" channel is a bool, both branches are valid and write the same channels"""
    def invalid(reason):
        dbc.raise_error({"msg": "INVALID_WORKFLOW", "reason": f"if node \"{node_name}\": {reason}"})

    condition = node["if"]
    condition_def = workflow["input"].get(condition) or workflow["bind"].get(condition) or workflow["connect"].get(condition)
    if condition_def is None:
        invalid(f"the condition channel \"{condition}\" is not defined")
    if condition_def["type"] != "bool":
        invalid(f"the condition channel \"{condition}\" must be of type bool, not {condition_def['type']}")
    output_def_of_channel = {}  # branch -> channel -> definition of the branch output writing it
    for branch in IF_BRANCHES:
        definition = _validate_used_node(node[branch], workflow)
        outputs = node[branch]["output"]
        if len(set(outputs.values())) != len(outputs):
            invalid(f"the {branch} branch writes a channel more than once")
        output_def_of_channel[branch] = {channel: definition["output"][name] for name, channel in outputs.items()}
    then_outputs, else_outputs = output_def_of_channel["then"], output_def_of_channel["else"]
    if set(then_outputs) != set(else_outputs):
        invalid(f"both branches must write the same channels (then: {sorted(then_outputs)}, else: {sorted(else_outputs)})")
    for channel, then_def in then_outputs.items():
        else_def = else_outputs[channel]
        if (then_def["type"], then_def.get("format")) != (else_def["type"], else_def.get("format")):
            invalid(f"channel \"{channel}\" is written with different type or format by the branches "
                    f"({then_def['type']}/{then_def.get('format')} and {else_def['type']}/{else_def.get('format')})")

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
    n.validate_channel_types(refinement.get("replace_bind"), "bind")
    _default_format_of_constant_binds(refinement.get("replace_bind"))
    h.validate_user_input( refinement, "refine_def")
    hash_of_workflow = get_workflow_hash_by_referer(refinement["workflow"])
    workflow_to_be_refined = db._workflow[hash_of_workflow]
    workflow = copy.deepcopy(workflow_to_be_refined)
    workflow_to_be_refined = {}
    workflow["name"] = refinement["name"]
    for key in list(workflow.keys()):
        if key and key[0] == "_":
           del workflow[key]
    for node_def in used_nodes(workflow["nodes"]).values():
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
    dbc.assert_true("if" not in node_def_to_be_replaced, {"msg": "REFINE_MISMATCH"})  # if nodes can't be replaced (yet)
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


def _freeze_data_binds(binds: dict) -> None:
    """
    The data of a bind is referenced by name and the version used now: "latest" and a hash are replaced.
    The data must exist when the workflow is stored.
    """
    for bind in binds.values():
        if isinstance(bind, dict) and "data" in bind:
            data = d.get_data_by_hash(d.get_data_hash_by_referer(bind["data"]))
            bind["data"] = {"name": data["name"], "version": str(data["_version"])}


def _definition_of_used_node(node: dict) -> dict:
    """the definition of a node or sub workflow used in a workflow (after _validate_used_node)"""
    if "_hash_of_node_def" in node:
        return n.get_node_by_hash(node["_hash_of_node_def"])
    return get_workflow_by_hash(node["_hash_of_workflow_def"])


def _normalize_written_formats(workflow: dict) -> None:
    """
    The format of a connect or output channel is the format of the node output writing it (the format given
    in the workflow is replaced). For an if node the then branch is used: both branches write the channels
    with equal formats.
    """
    for node in workflow["nodes"].values():
        used = node["then"] if "if" in node else node
        output_defs = _definition_of_used_node(used)["output"]
        for output_name, channel in used["output"].items():
            for section in ("connect", "output"):
                channel_def = workflow[section].get(channel)
                if channel_def is not None and output_name in output_defs and "format" in output_defs[output_name]:
                    channel_def["format"] = output_defs[output_name]["format"]


def _default_format_of_constant_binds(binds) -> None:
    """
    For binds of a constant type (str, int, float, bool, json) the format is optional: it defaults to "str".
    """
    if not isinstance(binds, dict):
        return
    for bind in binds.values():
        if isinstance(bind, dict) and bind.get("type") in n.CONSTANT_TYPES:
            bind.setdefault("format", "str")


def _validate_bind_values(binds: dict) -> None:
    """
    Validates that binds of constant types (str, int, float, bool, json) carry a "value" of the
    matching JSON type, and that a "value" is used for constant types only.

    Raises:
        Raises an error if a bind is invalid.
    """
    for channel_name, bind in binds.items():
        channel_type = bind.get("type")
        if channel_type in n.CONSTANT_TYPES:
            dbc.assert_true(
                "value" in bind,
                {"msg": "INVALID_CHANNEL_USE", "name": channel_name, "reason": f"a bind of type \"{channel_type}\" needs a \"value\""}
            )
            dbc.assert_true(
                h.value_matches_type(bind["value"], channel_type),
                {"msg": "INVALID_CONSTANT", "name": channel_name, "type": channel_type}
            )
        else:
            dbc.assert_true(
                "value" not in bind,
                {"msg": "INVALID_CHANNEL_USE", "name": channel_name, "reason": f"a bind of type \"{channel_type}\" can't have a \"value\""}
            )


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
        for channel in node_input_channels(node):
            if channel not in input_output_connections:
                input_output_connections[channel] = {
                "output": set(),
                "input": set(),
            }
            input_output_connections[channel]["input"].add(node_name)
        for channel in node_output_channels(node):
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
    # every node is part of the graph, also nodes without connections. Otherwise they would never run
    graph = {node_name: set() for node_name in workflow["nodes"]}
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

    try:
        ts = TopologicalSorter(graph)
        return list(ts.static_order())
    except CycleError:
        dbc.raise_error(
            {"msg": "INVALID_WORKFLOW", "reason": "cycle in operators in workflow"}
        )
