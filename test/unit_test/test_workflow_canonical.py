import pytest

import component.workflow as wf
import intern.database as db
import intern.dbc as dbc


def _def(name, version, outputs):
    return {"name": name, "_version": version, "input": {"m": {"type": "file", "format": "json"}},
            "output": {o: {"type": "file", "format": f} for o, f in outputs.items()}}


@pytest.fixture(autouse=True)
def tables(monkeypatch):
    monkeypatch.setattr(db, "_node", {"n1": _def("nd", 1, {"out": "json"}), "n2": _def("nd", 2, {"out": "csv"})})
    monkeypatch.setattr(db, "_workflow", {"w1": _def("sub", 1, {"out": "json"}), "w3": _def("sub", 3, {"out": "pkl"})})
    monkeypatch.setattr(db, "_data", {"d1aaaa": {"name": "iris", "_version": 1}, "d2bbbb": {"name": "iris", "_version": 2}})


def _workflow(node):
    return {"input": {"i": {"type": "file", "format": "any"}}, "output": {"o": {"type": "file", "format": "any"}},
            "bind": {}, "connect": {"c": {"type": "file", "format": "any"}}, "nodes": {"a": node}}


@pytest.mark.parametrize("version, frozen", [("latest", "2"), (1, "1"), ("1", "1")])
def test_node_version_is_frozen(version, frozen):
    node = {"node": {"name": "nd", "version": version}, "input": {"m": "i"}, "output": {"out": "o"}}
    wf._validate_used_node(node, _workflow(node))
    assert node["node"]["version"] == frozen
    assert node["_hash_of_node_def"] == ("n2" if frozen == "2" else "n1")


def test_sub_workflow_version_is_frozen():
    node = {"workflow": {"name": "sub", "version": "latest"}, "input": {"m": "i"}, "output": {"out": "o"}}
    wf._validate_used_node(node, _workflow(node))
    assert node["workflow"]["version"] == "3"


def test_data_binds_are_frozen():
    binds = {"latest": {"type": "file", "data": {"name": "iris", "version": "latest"}},
             "by_hash": {"type": "file", "data": {"hash": "d1aa"}},
             "number": {"type": "file", "data": {"name": "iris", "version": 2}},
             "constant": {"type": "int", "value": 3}}
    wf._freeze_data_binds(binds)
    assert binds["latest"]["data"] == {"name": "iris", "version": "2"}
    assert binds["by_hash"]["data"] == {"name": "iris", "version": "1"}
    assert binds["number"]["data"] == {"name": "iris", "version": "2"}
    assert binds["constant"] == {"type": "int", "value": 3}


def test_missing_data_is_an_error():
    with pytest.raises(dbc.ParmaException):
        wf._freeze_data_binds({"x": {"type": "file", "data": {"name": "unknown", "version": "latest"}}})


def test_formats_of_written_channels_are_normalized():
    workflow = _workflow({"node": {"name": "nd", "version": "1"}, "_hash_of_node_def": "n2",
                          "input": {"m": "i"}, "output": {"out": "c"}})
    workflow["nodes"]["b"] = {"workflow": {"name": "sub", "version": "3"}, "_hash_of_workflow_def": "w3",
                              "input": {"m": "c"}, "output": {"out": "o"}}
    wf._normalize_written_formats(workflow)
    assert workflow["connect"]["c"]["format"] == "csv"
    assert workflow["output"]["o"]["format"] == "pkl"
    assert workflow["input"]["i"]["format"] == "any"  # inputs (and binds) are the user's choice


def test_formats_written_by_if_nodes_are_normalized():
    workflow = _workflow({"if": "i",
                          "then": {"node": {"name": "nd", "version": "1"}, "_hash_of_node_def": "n1",
                                   "input": {"m": "i"}, "output": {"out": "o"}},
                          "else": {"workflow": {"name": "sub", "version": "1"}, "_hash_of_workflow_def": "w1",
                                   "input": {"m": "i"}, "output": {"out": "o"}}})
    wf._normalize_written_formats(workflow)
    assert workflow["output"]["o"]["format"] == "json"
