import copy

import pytest

import component.workflow as wf
import intern.database as db


def _workflow(pos_a=(10, 20), pos_in=(0, 0), value=3, input_order=("x", "y")):
    inputs = {"x": {"type": "file", "format": "any", "litegraph": {"pos": list(pos_in)}},
              "y": {"type": "int", "format": "any"}}
    return {
        "name": "wf_example",
        "nodes": {"a": {"node": {"name": "n", "version": 1}, "input": {"in": "x", "count": "y"}, "output": {"out": "o"},
                        "litegraph": {"pos": list(pos_a), "state": "expanded"}}},
        "input": {name: inputs[name] for name in input_order},
        "output": {"o": {"type": "file", "format": "any", "litegraph": {"pos": [300, 0]}}},
        "bind": {"c": {"type": "int", "format": "any", "value": value, "litegraph": {"pos": [0, 100]}}},
        "connect": {},
    }


def test_hash_ignores_layout_and_order():
    assert wf.workflow_hash(_workflow()) == wf.workflow_hash(_workflow(pos_a=(500, 600), pos_in=(7, 8)))
    assert wf.workflow_hash(_workflow()) == wf.workflow_hash(_workflow(input_order=("y", "x")))


def test_hash_depends_on_semantics():
    assert wf.workflow_hash(_workflow()) != wf.workflow_hash(_workflow(value=4))


def test_without_layout_doesnt_modify_its_argument():
    workflow = _workflow()
    original = copy.deepcopy(workflow)
    wf._without_layout(workflow)
    assert workflow == original


def test_semantics_ignores_metadata():
    stored = dict(_workflow(), _version=2, _date="2026-01-01", _hash_of_creating_user="u", _topological_order=["a"])
    assert wf._semantics(stored) == wf._semantics(_workflow(pos_a=(1, 1)))


@pytest.fixture
def store(monkeypatch):
    monkeypatch.setattr(db, "_workflow", {})
    monkeypatch.setattr(wf, "prepare_workflow", lambda workflow: None)  # needs node definitions otherwise
    return db._workflow


def test_save_layout_only_keeps_hash_version_and_date(store):
    base_hash, layout_only = wf.save_workflow(_workflow(), None, "user1")
    assert not layout_only
    date = store[base_hash]["_date"]

    moved = _workflow(pos_a=(500, 600), input_order=("y", "x"))
    hash_value, layout_only = wf.save_workflow(moved, base_hash, "user2")
    assert layout_only and hash_value == base_hash and len(store) == 1
    stored = store[base_hash]
    assert stored["nodes"]["a"]["litegraph"]["pos"] == [500, 600]
    assert list(stored["input"]) == ["y", "x"]
    assert stored["_version"] == 1 and stored["_date"] == date and stored["_hash_of_creating_user"] == "user1"


def test_save_removed_layout_is_removed(store):
    base_hash, _ = wf.save_workflow(_workflow(), None, "user1")
    without_pos = _workflow()
    del without_pos["bind"]["c"]["litegraph"]
    wf.save_workflow(without_pos, base_hash, "user1")
    assert "litegraph" not in store[base_hash]["bind"]["c"]


def test_save_semantic_change_creates_new_version(store):
    base_hash, _ = wf.save_workflow(_workflow(), None, "user1")
    hash_value, layout_only = wf.save_workflow(_workflow(value=4, pos_a=(1, 1)), base_hash, "user1")
    assert not layout_only and hash_value != base_hash
    assert store[hash_value]["_version"] == 2
    assert store[base_hash]["nodes"]["a"]["litegraph"]["pos"] == [10, 20]  # old version unchanged
