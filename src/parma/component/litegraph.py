"""
Conversion between the backend workflow format and the graph format of the LiteGraph editor.

LiteGraph node types used:
- "parma/<name>:<version>"   a node definition (see route /nodes/litegraph)
- "wf/<name>:<version>"      a workflow used as sub workflow (see route /nodes/litegraph)
- "core/infile"              bind of a file from the data store         -> "bind" with "data"
- "core/outfile"             output saved in the data store             -> "output"
- "core/wf_input"            input of the workflow (used as sub workflow) -> "input". Type and format
                             are taken from the node inputs it is connected to (all must be equal)
- "core/env_var_value"       value of an environment variable           -> "bind" with "environment_var_value"
- "core/<constant type>"     constant of type str, int, float, bool, json -> "bind" with "value"
- "core/if"                  an if node -> workflow node with "if", "then" and "else". Its slots:
                             input "condition" (bool), inputs "then.<input>" and "else.<input>" of the two
                             branches, one output per pair of branch outputs (named like the then output).
                             Properties: "then" and "else" (the litegraph types "parma/..." or "wf/..." of the
                             branches) and "out_pairs" ([[then output, else output], ...], in slot order)

An unconnected constant input of a parma node shows a widget in the editor. Its value is stored in the
node property named like the input and becomes a "bind" WITHOUT "litegraph". When a workflow is loaded,
such a bind (constant type, no position, read by exactly one node) is shown as widget value again.

The optional "litegraph" object of workflow nodes, inputs, binds and outputs keeps the layout of the
canvas: {"pos": [x, y], "state": "expanded" | "collapsed"}. A missing "state" means "expanded".
"""

import json
import re

import intern.dbc as dbc
import component.node as n
import component.data as d
import component.workflow as wf

NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")
PARMA_PREFIX = "parma/"
WF_PREFIX = "wf/"
IF_TYPE = "core/if"
IF_CONDITION = "condition"
WF_NODE_NAME_PROPERTY = "wf_node_name"
STATE_EXPANDED = "expanded"
STATE_COLLAPSED = "collapsed"

_CORE_SLOTS = {
    "core/infile":        ([], [("data", "file")]),
    "core/outfile":       ([("data", "file")], []),
    "core/env_var_value": ([], [("value", "environment_var")]),
    "core/wf_input":      ([], [("value", "*")]),  # "*": any type, set to the type of the channel
}
for _t in n.CONSTANT_TYPES:
    _CORE_SLOTS["core/" + _t] = ([], [("value", _t)])

_DEFAULT_VALUE = {"str": "", "int": 0, "float": 0.0, "bool": False, "json": ""}


def _error(reason: str):
    dbc.raise_error({"msg": "INVALID_WORKFLOW", "reason": reason})


# -- backend workflow -> litegraph ----------------------------------------------------------------

def workflow_to_litegraph(workflow: dict) -> dict:
    """
    Converts a stored workflow into a serialized LiteGraph graph (as accepted by LGraph.configure).

    Args:
        workflow (dict): A workflow as stored in the backend (nodes enriched with "_hash_of_node_def").

    Returns:
        dict: The serialized graph.
    """
    graph = _GraphBuilder()
    views = {wf_node_name: _lg_view_of_wf_node(wf_node) for wf_node_name, wf_node in workflow["nodes"].items()}

    # which nodes read a channel: channel -> [(workflow node name, litegraph input name)]
    readers = {}
    for wf_node_name, view in views.items():
        for node_channel, channel in view["input_map"].items():
            readers.setdefault(channel, []).append((wf_node_name, node_channel))

    # parma nodes, sub workflows and if nodes
    order = [name for name in workflow.get("_topological_order") or [] if name in workflow["nodes"]]
    order += [name for name in workflow["nodes"] if name not in order]
    # for nodes without position: columns by dependency level
    source_node_of = {channel: name for name, view in views.items() for channel in view["output_map"].values()}
    auto_layout = _AutoLayout()
    lg_node_of = {}       # workflow node name -> litegraph node
    source_of = {}        # channel -> (litegraph node, output slot)
    widget_binds = set()  # bind channels shown as widget values
    for wf_node_name in order:
        wf_node = workflow["nodes"][wf_node_name]
        view = views[wf_node_name]
        outputs = view["outputs"]
        pos = _stored_pos(wf_node) or auto_layout.position(wf_node_name, view["input_map"].values(), source_node_of)
        lg_node = graph.add_node(view["type"], pos, view["inputs"], outputs,
                                 dict(view["properties"], **{WF_NODE_NAME_PROPERTY: wf_node_name}))
        _set_state(lg_node, wf_node)
        lg_node_of[wf_node_name] = lg_node
        for node_channel, channel in view["output_map"].items():
            source_of[channel] = (lg_node, _slot_index(outputs, node_channel))
        for node_channel, channel in view["input_map"].items():
            bind = workflow["bind"].get(channel)
            if bind and bind["type"] in n.CONSTANT_TYPES and _stored_pos(bind) is None and len(readers[channel]) == 1:
                lg_node["properties"][node_channel] = _value_for_widget(bind["value"], bind["type"])
                widget_binds.add(channel)

    # inputs of the workflow
    free_y = {}
    for channel, input_def in (workflow.get("input") or {}).items():
        pos = _stored_pos(input_def) or _pos_left_of(lg_node_of, readers.get(channel, []), free_y)
        lg_node = graph.add_node("core/wf_input", pos, [], [("value", input_def["type"])], {"name": channel})
        _set_state(lg_node, input_def)
        source_of[channel] = (lg_node, 0)

    # binds that are shown as core nodes
    for channel, bind in workflow["bind"].items():
        if channel in widget_binds:
            continue
        pos = _stored_pos(bind) or _pos_left_of(lg_node_of, readers.get(channel, []), free_y)
        if "data" in bind:
            name, version = _data_name_and_version(bind["data"])
            lg_node = graph.add_core_node("core/infile", pos, {"name": name, "version": version})
        elif "environment_var_value" in bind:
            lg_node = graph.add_core_node("core/env_var_value", pos, {"value": bind["environment_var_value"]})
        elif "value" in bind:
            lg_node = graph.add_core_node("core/" + bind["type"], pos,
                                          {"value": _value_for_widget(bind["value"], bind["type"])})
        else:
            _error(f"bind \"{channel}\" can't be shown graphically")
        _set_state(lg_node, bind)
        source_of[channel] = (lg_node, 0)

    # links from sources to the inputs of parma nodes
    for wf_node_name, view in views.items():
        target = lg_node_of[wf_node_name]
        for node_channel, channel in view["input_map"].items():
            if channel in widget_binds:
                continue
            if channel not in source_of:
                _error(f"channel \"{channel}\" has no source")
            source, source_slot = source_of[channel]
            graph.add_link(source, source_slot, target, _slot_index_of_lg(target["inputs"], node_channel))

    # outputs saved in the data store
    for channel, output_def in workflow["output"].items():
        if channel not in source_of:
            continue
        source, source_slot = source_of[channel]
        pos = _stored_pos(output_def) or [source["pos"][0] + 300, source["pos"][1] + 40 * source_slot]
        lg_node = graph.add_core_node("core/outfile", pos, {"name": channel})
        _set_state(lg_node, output_def)
        graph.add_link(source, source_slot, lg_node, 0)

    return graph.serialize()


def _lg_view_of_wf_node(wf_node: dict) -> dict:
    """
    How a workflow node is shown in litegraph:
        type        the litegraph node type
        inputs      [(litegraph input name, type)]
        outputs     [(litegraph output name, type)]
        properties  the litegraph properties needed (besides the workflow node name)
        input_map   litegraph input name -> workflow channel read
        output_map  litegraph output name -> workflow channel written
    A node or sub workflow uses the channel names of its definition. An if node gets an input
    "condition", the inputs of the branches prefixed by "then." and "else." and one output per pair
    of branch outputs. Outputs of the branches writing the same channel form a pair. Unbound outputs
    are paired in the order of their definition.
    """
    if "if" not in wf_node:
        prefix, node_def = _definition_of_wf_node(wf_node)
        return {
            "type": _lg_type_of(prefix, node_def),
            "inputs": [(ch, meta["type"]) for ch, meta in node_def["input"].items()],
            "outputs": [(ch, meta["type"]) for ch, meta in node_def["output"].items()],
            "properties": {},
            "input_map": dict(wf_node["input"]),
            "output_map": dict(wf_node["output"]),
        }
    inputs = [(IF_CONDITION, "bool")]
    input_map = {IF_CONDITION: wf_node["if"]}
    properties = {}
    definitions = {}
    for branch in wf.IF_BRANCHES:
        prefix, branch_def = _definition_of_wf_node(wf_node[branch])
        definitions[branch] = branch_def
        properties[branch] = _lg_type_of(prefix, branch_def)
        inputs += [(f"{branch}.{ch}", meta["type"]) for ch, meta in branch_def["input"].items()]
        input_map.update({f"{branch}.{ch}": channel for ch, channel in wf_node[branch]["input"].items()})
    then_def, else_def = definitions["then"], definitions["else"]
    then_out, else_out = wf_node["then"]["output"], wf_node["else"]["output"]
    else_name_of_channel = {channel: name for name, channel in else_out.items()}
    pairs = [[name, else_name_of_channel[channel]] for name, channel in then_out.items() if channel in else_name_of_channel]
    unbound_then = [name for name in then_def["output"] if name not in then_out]
    unbound_else = [name for name in else_def["output"] if name not in else_out]
    pairs += [list(pair) for pair in zip(unbound_then, unbound_else)]
    properties["out_pairs"] = pairs
    return {
        "type": IF_TYPE,
        "inputs": inputs,
        "outputs": [(then_name, then_def["output"][then_name]["type"]) for then_name, _ in pairs],
        "properties": properties,
        "input_map": input_map,
        "output_map": {name: channel for name, channel in then_out.items() if channel in else_name_of_channel},
    }


def _lg_type_of(prefix: str, definition: dict) -> str:
    return f"{prefix}{definition['name']}:{definition['_version']}"


def _definition_of_wf_node(wf_node: dict) -> tuple:
    """(litegraph type prefix, definition) of a workflow node: a node definition or a sub workflow"""
    if "node" in wf_node:
        return PARMA_PREFIX, n.get_node_by_hash(wf_node.get("_hash_of_node_def") or n.get_node_hash_by_referer(wf_node["node"]))
    if "workflow" in wf_node:
        return WF_PREFIX, wf.get_workflow_by_hash(wf_node.get("_hash_of_workflow_def")
                                                  or wf.get_workflow_hash_by_referer(wf_node["workflow"]))
    _error("a workflow node needs \"node\" or \"workflow\"")


def _slot_index(slots: list, name: str) -> int:
    for i, (slot_name, _) in enumerate(slots):
        if slot_name == name:
            return i
    _error(f"channel \"{name}\" not found in node definition")


def _slot_index_of_lg(slots: list, name: str) -> int:
    return _slot_index([(s["name"], s["type"]) for s in slots], name)


def _pos_left_of(lg_node_of: dict, readers: list, free_y: dict) -> list:
    """position for a core node without position: left of the first node reading it, stacked downwards"""
    if not readers:
        return [50, 50]
    target = lg_node_of[readers[0][0]]
    x = target["pos"][0] - 250
    y = free_y.get(x, target["pos"][1])
    free_y[x] = y + 90
    return [x, y]


def _data_name_and_version(data_referer: dict) -> tuple:
    if "hash" in data_referer:
        data = d.get_data_by_hash(d.get_data_hash_by_referer(data_referer))
        return data["name"], str(data["_version"])
    return data_referer["name"], str(data_referer["version"])


def _value_for_widget(value, channel_type: str):
    """json is edited in a text widget, thus non-strings are shown as JSON text"""
    if channel_type == "json" and not isinstance(value, str):
        return json.dumps(value)
    return value


class _AutoLayout:
    """places nodes in columns: a node is right of all nodes it reads from. Leaves room for input nodes left of it"""
    COLUMN_WIDTH = 520
    ROW_HEIGHT = 220

    def __init__(self):
        self.level = {}
        self.rows = {}

    def position(self, wf_node_name, input_channels, source_node_of):
        level = 0
        for channel in input_channels:
            writer = source_node_of.get(channel)
            if writer in self.level:
                level = max(level, self.level[writer] + 1)
        self.level[wf_node_name] = level
        row = self.rows.get(level, 0)
        self.rows[level] = row + 1
        return [320 + level * self.COLUMN_WIDTH, 80 + row * self.ROW_HEIGHT]


class _GraphBuilder:
    def __init__(self):
        self.nodes = []
        self.links = []

    def add_node(self, lg_type, pos, inputs, outputs, properties):
        lg_node = {
            "id": len(self.nodes) + 1,
            "type": lg_type,
            "pos": list(pos),
            "flags": {},
            "order": len(self.nodes),
            "mode": 0,
            "inputs": [{"name": name, "type": t, "link": None} for name, t in inputs],
            "outputs": [{"name": name, "type": t, "links": []} for name, t in outputs],
            "properties": properties,
        }
        self.nodes.append(lg_node)
        return lg_node

    def add_core_node(self, lg_type, pos, properties):
        inputs, outputs = _CORE_SLOTS[lg_type]
        return self.add_node(lg_type, pos, inputs, outputs, properties)

    def add_link(self, source, source_slot, target, target_slot):
        link_id = len(self.links) + 1
        link_type = source["outputs"][source_slot]["type"]
        self.links.append([link_id, source["id"], source_slot, target["id"], target_slot, link_type])
        source["outputs"][source_slot]["links"].append(link_id)
        target["inputs"][target_slot]["link"] = link_id

    def serialize(self):
        return {
            "last_node_id": len(self.nodes),
            "last_link_id": len(self.links),
            "nodes": self.nodes,
            "links": self.links,
            "groups": [],
            "config": {},
            "extra": {},
            "version": 0.4,
        }


# -- litegraph -> backend workflow ----------------------------------------------------------------

def litegraph_to_workflow(name: str, graph: dict) -> dict:
    """
    Converts a serialized LiteGraph graph into a workflow in the backend format.
    The result still has to be validated and stored by workflow.add_workflow().

    Args:
        name (str): The name of the workflow.
        graph (dict): The serialized graph (result of LGraph.serialize()).

    Returns:
        dict: The workflow.
    """
    if not isinstance(name, str) or not NAME_PATTERN.match(name):
        dbc.raise_error({"msg": "INVALID_NAME"})
    lg_nodes = {lg_node["id"]: lg_node for lg_node in graph.get("nodes") or []}
    links = {}
    for link in graph.get("links") or []:
        if isinstance(link, dict):
            link = [link["id"], link["origin_id"], link["origin_slot"], link["target_id"], link["target_slot"]]
        links[link[0]] = {"origin_id": link[1], "origin_slot": link[2], "target_id": link[3], "target_slot": link[4]}

    workflow = {"name": name, "input": {}, "output": {}, "bind": {}, "connect": {}, "nodes": {}}
    names = _UniqueNames()       # channel names
    node_names = _UniqueNames()  # workflow node names

    # workflow nodes for parma nodes, sub workflows and if nodes. An if node is first collected like a
    # parma node with a definition combined from its branches, at the end it gets its final form
    wf_node_name_of = {}
    node_def_of = {}
    if_nodes = {}  # litegraph id -> {"then"|"else": (kind, referer, definition), "out_pairs": ...}
    for lg_id, lg_node in lg_nodes.items():
        lg_type = lg_node.get("type", "")
        if lg_type.startswith(PARMA_PREFIX) or lg_type.startswith(WF_PREFIX):
            kind, referer, node_def_of[lg_id] = _referer_and_definition_of_lg_type(lg_type)
            proposal = (lg_node.get("properties") or {}).get(WF_NODE_NAME_PROPERTY) or f"{referer['name']}_{lg_id}"
            wf_node_name = node_names.reserve(proposal)
            wf_node_name_of[lg_id] = wf_node_name
            workflow["nodes"][wf_node_name] = {
                kind: referer,
                "input": {},
                "output": {},
                "litegraph": _litegraph_of(lg_node),
            }
        elif lg_type == IF_TYPE:
            proposal = (lg_node.get("properties") or {}).get(WF_NODE_NAME_PROPERTY) or f"if_{lg_id}"
            wf_node_name = node_names.reserve(proposal)
            wf_node_name_of[lg_id] = wf_node_name
            if_nodes[lg_id], node_def_of[lg_id] = _if_node_info(wf_node_name, lg_node)
            workflow["nodes"][wf_node_name] = {"input": {}, "output": {}, "litegraph": _litegraph_of(lg_node)}
        elif lg_type not in _CORE_SLOTS:
            _error(f"node type \"{lg_type}\" is unknown")

    channel_of_source = {}  # (litegraph node id, output slot) -> channel

    def channel_for_source(origin_id, origin_slot, target_meta, target_input_name):
        key = (origin_id, origin_slot)
        source = lg_nodes[origin_id]
        props = source.get("properties") or {}
        source_type = source["type"]
        if key in channel_of_source:
            channel = channel_of_source[key]
            if source_type == "core/wf_input":
                input_def = workflow["input"][channel]
                if (input_def["type"], input_def["format"]) != (target_meta["type"], target_meta["format"]):
                    _error(f"workflow input \"{channel}\" is connected to inputs of different type or format "
                           f"({input_def['type']}/{input_def['format']} and {target_meta['type']}/{target_meta['format']})")
            return channel
        if source_type == "core/wf_input":
            input_name = props.get("name", "")
            if not NAME_PATTERN.match(input_name or ""):
                _error(f"workflow input name \"{input_name}\" is invalid")
            channel = names.reserve(input_name, must_be_unchanged=True)
            workflow["input"][channel] = {"type": target_meta["type"], "format": target_meta["format"],
                                          "litegraph": _litegraph_of(source)}
        elif source_type == "core/infile":
            data_name, data_version = props.get("name", ""), props.get("version", "")
            if not data_name or not data_version:
                _error("an input file needs name and version")
            channel = names.reserve(data_name)
            workflow["bind"][channel] = {"type": target_meta["type"], "format": target_meta["format"],
                                         "data": {"name": data_name, "version": str(data_version)}, "litegraph": _litegraph_of(source)}
        elif source_type == "core/env_var_value":
            channel = names.reserve(target_input_name)
            workflow["bind"][channel] = {"type": "environment_var", "format": target_meta["format"],
                                         "environment_var_value": str(props.get("value", "")), "litegraph": _litegraph_of(source)}
        elif source_type.startswith("core/") and source_type[len("core/"):] in n.CONSTANT_TYPES:
            constant_type = source_type[len("core/"):]
            channel = names.reserve(target_input_name)
            workflow["bind"][channel] = {"type": constant_type, "format": target_meta["format"],
                                         "value": _value_from_widget(props.get("value"), constant_type, channel),
                                         "litegraph": _litegraph_of(source)}
        elif origin_id in wf_node_name_of:
            source_name = wf_node_name_of[origin_id]
            output_name = source["outputs"][origin_slot]["name"]
            output_meta = node_def_of[origin_id]["output"][output_name]
            channel = names.reserve(f"{source_name}_{output_name}")
            workflow["connect"][channel] = {"type": output_meta["type"], "format": output_meta["format"]}
            workflow["nodes"][source_name]["output"][output_name] = channel
        else:
            _error(f"node type \"{source_type}\" can't be the source of a link")
        channel_of_source[key] = channel
        return channel

    # outputs of parma nodes connected to output files
    for lg_id, wf_node_name in wf_node_name_of.items():
        lg_node = lg_nodes[lg_id]
        for slot, output in enumerate(lg_node.get("outputs") or []):
            targets = [links[link_id] for link_id in (output.get("links") or []) if link_id in links]
            outfiles = [t for t in targets if lg_nodes[t["target_id"]]["type"] == "core/outfile"]
            if not outfiles:
                continue
            if len(targets) > 1:
                _error(f"output \"{output['name']}\" of node \"{wf_node_name}\" is saved as file, "
                       f"thus it can't be connected to other nodes")
            outfile = lg_nodes[outfiles[0]["target_id"]]
            file_name = (outfile.get("properties") or {}).get("name", "")
            if not NAME_PATTERN.match(file_name or ""):
                _error(f"output file name \"{file_name}\" is invalid")
            channel = names.reserve(file_name, must_be_unchanged=True)
            output_meta = node_def_of[lg_id]["output"][output["name"]]
            if output_meta["type"] == "directory":
                _error(f"output \"{output['name']}\" of node \"{wf_node_name}\" is a directory. Not supported by the editor")
            workflow["output"][channel] = {"type": output_meta["type"], "format": output_meta["format"],
                                           "litegraph": _litegraph_of(outfile)}
            workflow["nodes"][wf_node_name]["output"][output["name"]] = channel
            channel_of_source[(lg_id, slot)] = channel

    # inputs of parma nodes: links or widget values
    for lg_id, wf_node_name in wf_node_name_of.items():
        lg_node = lg_nodes[lg_id]
        node_def = node_def_of[lg_id]
        props = lg_node.get("properties") or {}
        for lg_input in lg_node.get("inputs") or []:
            input_name = lg_input["name"]
            input_meta = node_def["input"].get(input_name)
            if input_meta is None:
                _error(f"input \"{input_name}\" of node \"{wf_node_name}\" doesn't match the node definition")
            channel_proposal = input_name.rpartition(".")[2]  # without the prefix "then." or "else." of if nodes
            link = links.get(lg_input.get("link"))
            if link:
                channel = channel_for_source(link["origin_id"], link["origin_slot"], input_meta, channel_proposal)
            elif input_meta["type"] in n.CONSTANT_TYPES:
                channel = names.reserve(channel_proposal)
                value = props.get(input_name, _DEFAULT_VALUE[input_meta["type"]])
                workflow["bind"][channel] = {"type": input_meta["type"], "format": input_meta["format"],
                                             "value": _value_from_widget(value, input_meta["type"], channel)}
            else:
                continue  # not connected: reported as warning when the workflow is stored
            workflow["nodes"][wf_node_name]["input"][input_name] = channel

    for lg_node in lg_nodes.values():
        if lg_node.get("type") == "core/wf_input" and not any(
                links.get(link_id) for link_id in ((lg_node.get("outputs") or [{}])[0].get("links") or [])):
            name_of_input = (lg_node.get("properties") or {}).get("name", "")
            _error(f"workflow input \"{name_of_input}\" is not connected")
    for lg_id, info in if_nodes.items():
        wf_node_name = wf_node_name_of[lg_id]
        workflow["nodes"][wf_node_name] = _final_if_node(wf_node_name, workflow["nodes"][wf_node_name], info)
    if not workflow["nodes"]:
        _error("the workflow has no nodes")
    # the order of the inputs and outputs of the workflow (e.g. of the slots of a sub workflow) is the
    # vertical order of their nodes in the editor: top first (same height: left first, then by name)
    for key in ("input", "output"):
        workflow[key] = dict(sorted(workflow[key].items(), key=lambda item: (item[1]["litegraph"]["pos"][1], item[1]["litegraph"]["pos"][0], item[0])))
    return workflow


def _referer_and_definition_of_lg_type(lg_type: str) -> tuple:
    """("node" | "workflow", referer, definition) of the litegraph type "parma/<name>:<version>" or "wf/<name>:<version>" """
    is_node = lg_type.startswith(PARMA_PREFIX)
    prefix = PARMA_PREFIX if is_node else WF_PREFIX
    name, _, version = lg_type[len(prefix):].rpartition(":")
    referer = {"name": name, "version": version}
    if is_node:
        return "node", referer, n.get_node_by_hash(n.get_node_hash_by_referer(referer))
    return "workflow", referer, wf.get_workflow_by_hash(wf.get_workflow_hash_by_referer(referer))


def _if_node_info(wf_node_name: str, lg_node: dict) -> tuple:
    """
    (info, combined definition) of a litegraph if node. info: "then" and "else" -> (kind, referer,
    definition), "out_pairs" -> {then output: else output}. The combined definition has the slots of
    the litegraph node: inputs "condition", "then.<input>", "else.<input>", the then outputs of the pairs.
    """
    props = lg_node.get("properties") or {}
    info = {}
    combined = {"input": {IF_CONDITION: {"type": "bool", "format": "str"}}, "output": {}}
    for branch in wf.IF_BRANCHES:
        lg_type = props.get(branch) or ""
        if not (lg_type.startswith(PARMA_PREFIX) or lg_type.startswith(WF_PREFIX)):
            _error(f"if node \"{wf_node_name}\": the {branch} branch is not selected")
        info[branch] = _referer_and_definition_of_lg_type(lg_type)
        for name, meta in info[branch][2]["input"].items():
            combined["input"][f"{branch}.{name}"] = meta
    then_def, else_def = info["then"][2], info["else"][2]
    pairs = props.get("out_pairs") or []
    then_names = [pair[0] for pair in pairs]
    else_names = [pair[1] for pair in pairs]
    if sorted(then_names) != sorted(then_def["output"]) or sorted(else_names) != sorted(else_def["output"]):
        _error(f"if node \"{wf_node_name}\": the outputs of the branches don't match (select the branches again)")
    for then_name, else_name in pairs:
        combined["output"][then_name] = then_def["output"][then_name]
    info["out_pairs"] = dict((pair[0], pair[1]) for pair in pairs)
    return info, combined


def _final_if_node(wf_node_name: str, collected: dict, info: dict) -> dict:
    """the if node of the workflow made of the node collected like a parma node (with the slot names of litegraph)"""
    inputs = collected["input"]
    if IF_CONDITION not in inputs:
        _error(f"if node \"{wf_node_name}\": the condition is not connected")
    result = {"if": inputs[IF_CONDITION]}
    for branch in wf.IF_BRANCHES:
        kind, referer, _ = info[branch]
        prefix = branch + "."
        result[branch] = {
            kind: referer,
            "input": {name[len(prefix):]: channel for name, channel in inputs.items() if name.startswith(prefix)},
            "output": {(then_name if branch == "then" else info["out_pairs"][then_name]): channel
                       for then_name, channel in collected["output"].items()},
        }
    result["litegraph"] = collected["litegraph"]
    return result


def _stored_pos(definition: dict):
    """the position stored in "litegraph" of a workflow node, bind, input or output (None if missing).
    Definitions stored before the introduction of "litegraph" have a top level "pos"."""
    return (definition.get("litegraph") or {}).get("pos") or definition.get("pos")


def _set_state(lg_node: dict, definition: dict) -> None:
    """collapses the litegraph node, if the "state" stored in "litegraph" is "collapsed" (default: "expanded")"""
    if (definition.get("litegraph") or {}).get("state") == STATE_COLLAPSED:
        lg_node["flags"]["collapsed"] = True


def _litegraph_of(lg_node: dict) -> dict:
    """the layout data of a litegraph node stored in the workflow: position and state"""
    collapsed = bool((lg_node.get("flags") or {}).get("collapsed"))
    return {"pos": _pos(lg_node), "state": STATE_COLLAPSED if collapsed else STATE_EXPANDED}


def _pos(lg_node: dict) -> list:
    pos = lg_node.get("pos") or [0, 0]
    if isinstance(pos, dict):  # older litegraph versions serialize Float32Array as {"0": x, "1": y}
        pos = [pos.get("0", 0), pos.get("1", 0)]
    return [round(float(pos[0]), 1), round(float(pos[1]), 1)]


def _value_from_widget(value, constant_type: str, channel: str):
    """converts the value of a widget to the JSON value of a constant of the given type"""
    try:
        if constant_type == "str":
            return "" if value is None else str(value)
        if constant_type == "int":
            return int(value)
        if constant_type == "float":
            return float(value)
        if constant_type == "bool":
            return value if isinstance(value, bool) else str(value).lower() == "true"
        if constant_type == "json":
            return json.loads(value) if isinstance(value, str) else value
        return value
    except (TypeError, ValueError):
        dbc.raise_error({"msg": "INVALID_CONSTANT", "name": channel, "type": constant_type})


class _UniqueNames:
    """creates valid channel and node names, that are unique in a workflow"""

    def __init__(self):
        self.used = set()

    def reserve(self, proposal: str, must_be_unchanged: bool = False) -> str:
        base = re.sub(r"[^a-zA-Z0-9_]", "_", proposal or "")
        if not base or not base[0].isalpha():
            base = "c_" + base
        if must_be_unchanged and base in self.used:
            dbc.raise_error({"msg": "DUPLICATE_CHANNEL", "name": base})
        name = base
        counter = 2
        while name in self.used:
            name = f"{base}_{counter}"
            counter += 1
        self.used.add(name)
        return name
