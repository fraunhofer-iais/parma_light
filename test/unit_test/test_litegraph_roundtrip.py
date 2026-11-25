import copy

import pytest

import component.litegraph as lg
import component.workflow as wf


def _channels(**channels):
    return {name: {"type": t, "format": f} for name, (t, f) in channels.items()}


_DEFS = {
    "prep": {"name": "prep", "_version": 1,
             "input": _channels(data=("file", "json"), count=("int", "str")),
             "output": _channels(x=("file", "json"))},
    "train": {"name": "train", "_version": 1,
              "input": _channels(x=("file", "json"), rate=("float", "str"), secret=("environment_var", "any"),
                                 thr=("float", "str")),
              "output": _channels(model=("file", "json"))},
    "post_a": {"name": "post_a", "_version": 1, "input": _channels(m=("file", "json")),
               "output": _channels(r=("file", "json"))},
    "post_b": {"name": "post_b", "_version": 1, "input": _channels(m=("file", "json")),
               "output": _channels(res=("file", "json"))},
}


@pytest.fixture(autouse=True)
def node_definitions(monkeypatch):
    """node definitions without a store"""
    monkeypatch.setattr(lg, "_definition_of_wf_node", lambda wf_node: (lg.PARMA_PREFIX, _DEFS[wf_node["node"]["name"]]))

    def referer_and_definition(lg_type):
        name, _, version = lg_type[len(lg.PARMA_PREFIX):].rpartition(":")
        return "node", {"name": name, "version": version}, _DEFS[name]
    monkeypatch.setattr(lg, "_referer_and_definition_of_lg_type", referer_and_definition)


def _hand_written_workflow():
    """
    Canonical (as stored by workflow.prepare_workflow: frozen versions, connect/output formats of the writing
    nodes), but with hand-chosen channel names and input/bind formats that differ from the reading nodes
    """
    return {
        "name": "hand_written",
        "nodes": {
            "p": {"node": {"name": "prep", "version": "1"}, "input": {"data": "raw", "count": "n_items"},
                  "output": {"x": "features"}},
            "t": {"node": {"name": "train", "version": "1"},
                  "input": {"x": "features", "rate": "lr", "secret": "api_env", "thr": "threshold"},
                  "output": {"model": "trained"}},
            "choose": {"if": "use_a",
                       "then": {"node": {"name": "post_a", "version": "1"}, "input": {"m": "trained"},
                                "output": {"r": "report"}},
                       "else": {"node": {"name": "post_b", "version": "1"}, "input": {"m": "trained"},
                                "output": {"res": "report"}}},
        },
        "input": {"threshold": {"type": "float", "format": "any"}},                          # node input: "str"
        "output": {"report": {"type": "file", "format": "json"}},
        "bind": {
            "raw": {"type": "file", "format": "any", "data": {"name": "iris", "version": "1"}},  # node input: json
            "n_items": {"type": "int", "format": "any", "value": 5},                        # widget, node input: "str"
            "lr": {"type": "float", "format": "str", "value": 0.1, "litegraph": {"pos": [0, 0]}},  # constant node
            "api_env": {"type": "environment_var", "format": "any", "environment_var_value": "API_KEY"},
            "use_a": {"type": "bool", "format": "str", "value": True, "litegraph": {"pos": [0, 300]}},
        },
        "connect": {"features": {"type": "file", "format": "json"}, "trained": {"type": "file", "format": "json"}},
    }


def _round_trip(workflow):
    graph = lg.workflow_to_litegraph(copy.deepcopy(workflow))
    return lg.litegraph_to_workflow(workflow["name"], graph)


def test_round_trip_keeps_names_and_formats():
    original = _hand_written_workflow()
    assert wf._semantics(_round_trip(original)) == wf._semantics(original)


def test_round_trip_is_stable():
    once = _round_trip(_hand_written_workflow())
    assert wf._semantics(_round_trip(once)) == wf._semantics(once)


def test_graph_without_wf_properties_gets_invented_names_and_node_formats():
    """a graph built in the editor (no wf_... properties) gets generated names and the formats of the nodes"""
    graph = lg.workflow_to_litegraph(_hand_written_workflow())
    for node in graph["nodes"]:
        for key in [k for k in node["properties"] if k.startswith("wf_") and k != lg.WF_NODE_NAME_PROPERTY]:
            del node["properties"][key]
    result = lg.litegraph_to_workflow("hand_written", graph)
    assert set(result["bind"]) == {"iris", "count", "rate", "secret", "condition"}
    assert set(result["connect"]) == {"p_x", "t_model"}
    assert result["bind"]["iris"]["format"] == "json"
    assert result["input"]["threshold"]["format"] == "str"
