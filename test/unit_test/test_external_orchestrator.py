import pytest

import intern.database as db
import intern.dbc as dbc
import component.data as d
import component.external_orchestrator as eo


def _node(image=True, inputs=None, outputs=None):
    node = {"name": "nd", "_version": 1, "input": inputs or {}, "output": outputs or {}}
    if image:
        node["_image_id"] = "img:1"
    else:
        node["_bash_id"] = "bash-data-hash"
    return node


NODES = {
    "n_train": _node(
        inputs={"seed": {"type": "environment_var", "format": "str", "environment_var_in_container": "SEED"}},
        outputs={"model": {"type": "file", "format": "any", "path_in_container": "/data/model.pkl"}}),
    "n_predict": _node(
        inputs={"model": {"type": "file", "format": "any", "path_in_container": "/data/model.pkl"},
                "x": {"type": "file", "format": "any", "path_in_container": "/data/x.json"},
                "n": {"type": "int", "format": "int", "command_line_parameter": "--n"}},
        outputs={"pred": {"type": "file", "format": "any", "path_in_container": "/data/pred.json"}}),
    "n_bash": _node(image=False,
                    outputs={"pred": {"type": "file", "format": "any", "environment_var_in_container": "OUT"}}),
}


def _wf(name, nodes, order, input=None, output=None, bind=None, connect=None):
    return {"name": name, "_version": 1, "input": input or {}, "output": output or {}, "bind": bind or {},
            "connect": connect or {}, "nodes": nodes, "_topological_order": order}


FILE = {"type": "file", "format": "any"}


@pytest.fixture
def store(monkeypatch):
    workflows = {}
    monkeypatch.setattr(db, "_node", NODES)
    monkeypatch.setattr(db, "_workflow", workflows)
    monkeypatch.setattr(d, "get_data_hash_by_referer", lambda referer: "data-" + referer["name"])
    monkeypatch.setattr(d, "get_path_by_hash", lambda hash, for_mounting=False: f"/store/{hash}")
    return workflows


def _train_predict(predict_node="n_predict"):
    return _wf("train_predict", {
        "train": {"node": {"name": "nd_train", "version": "1"}, "_hash_of_node_def": "n_train",
                  "input": {"seed": "seed"}, "output": {"model": "model"}},
        "predict": {"node": {"name": "nd_predict", "version": "1"}, "_hash_of_node_def": predict_node,
                    "input": {"model": "model", "x": "x", "n": "count"}, "output": {"pred": "pred"}},
    }, ["train", "predict"],
        input={"count": {"type": "int", "format": "int"}},
        output={"pred": FILE},
        bind={"seed": {"type": "environment_var", "format": "str", "environment_var_value": "42"},
              "x": {"type": "file", "format": "any", "data": {"name": "x_test", "version": "latest"}}},
        connect={"model": FILE})


def test_simple_workflow(store):
    store["wf"] = _train_predict()
    snakefile = eo.parma2snakemake({"hash": "wf"})
    assert "rule train:" in snakefile
    assert "rule predict:" in snakefile
    assert "PARMA_TARGETS.append('parma_work/pred')" in snakefile
    assert "('SEED', parma_str('42'))" in snakefile
    assert "('parma_work/model', '/data/model.pkl')" in snakefile
    assert "('/store/data-x_test', '/data/x.json')" in snakefile
    assert "'--n', parma_str(config['count'])" in snakefile
    assert "--config count=..." in snakefile
    # outputs are stored as data named like the channel (as run.py does)
    assert "register=[('parma_work/model', 'model', 'platform', 'file', 'model')]" in snakefile
    assert "register=[('parma_work/pred', 'pred', 'platform', 'file', 'pred')]" in snakefile
    assert "PARMA_WORKFLOW_HASH = 'wf'" in snakefile
    assert "PARMA_RULE_ORDER = ['train', 'predict']" in snakefile
    assert "onsuccess:\n    parma_register_run(True, log)" in snakefile
    assert "onerror:\n    parma_register_run(False, log)" in snakefile
    assert "PARMA_RUN_NAME = 'train_predict'" in snakefile  # default: the workflow name
    assert "PARMA_RUN_NAME = 'run_x'" in eo.parma2snakemake({"hash": "wf"}, run_name="run_x")


def test_extern_output_is_registered_as_extern(store):
    workflow = _train_predict()
    workflow["output"]["pred"] = {"type": "file", "format": "any", "storage": "extern", "user_path": "/out/pred.json"}
    store["wf"] = workflow
    snakefile = eo.parma2snakemake({"hash": "wf"})
    assert "register=[('/out/pred.json', 'pred', 'extern', 'file', 'pred')]" in snakefile


def test_sub_workflow_is_inlined_with_prefix(store):
    store["sub"] = _train_predict()
    store["top"] = _wf("top", {
        "inner": {"workflow": {"name": "train_predict", "version": "1"}, "_hash_of_workflow_def": "sub",
                  "input": {"count": "c"}, "output": {"pred": "result"}},
    }, ["inner"], output={"result": FILE}, bind={"c": {"type": "int", "format": "int", "value": 3}})
    snakefile = eo.parma2snakemake({"hash": "top"})
    assert "rule inner__train:" in snakefile
    assert "rule inner__predict:" in snakefile
    assert "'parma_work/inner__model'" in snakefile
    assert "PARMA_TARGETS.append('parma_work/result')" in snakefile
    assert "'--n', parma_str(3)" in snakefile
    # data names are the channel names of the sub workflow, run channels are prefixed
    assert "register=[('parma_work/inner__model', 'model', 'platform', 'file', 'inner__model')]" in snakefile
    assert "register=[('parma_work/result', 'pred', 'platform', 'file', 'inner__pred')]" in snakefile
    assert "PARMA_RULE_ORDER = ['inner__train', 'inner__predict']" in snakefile


def test_if_node(store):
    branch = lambda node_hash: {"node": {"name": "nd", "version": "1"}, "_hash_of_node_def": node_hash,
                                "input": {"seed": "seed"}, "output": {"model": "model"}}
    store["wf"] = _wf("with_if", {"choose": {"if": "flag", "then": branch("n_train"), "else": branch("n_train")}},
                      ["choose"], input={"flag": {"type": "bool", "format": "bool"}}, output={"model": FILE},
                      bind={"seed": {"type": "str", "format": "str", "value": "1"}})
    snakefile = eo.parma2snakemake({"hash": "wf"})
    assert ("if parma_bool(config['flag']):\n    PARMA_LOG_PREAMBLE.append('if node \"choose\": condition \"flag\" "
            "is True, the then branch nd:1 is executed')\n    rule choose_then:") in snakefile
    assert ("else:\n    PARMA_LOG_PREAMBLE.append('if node \"choose\": condition \"flag\" is False, "
            "the else branch nd:1 is executed')\n    rule choose_else:") in snakefile


def test_bash_node_is_rejected(store):
    store["wf"] = _train_predict(predict_node="n_bash")
    with pytest.raises(dbc.ParmaException):
        eo.parma2snakemake({"hash": "wf"})


def test_bash_node_in_sub_workflow_is_rejected(store):
    store["sub"] = _train_predict(predict_node="n_bash")
    store["top"] = _wf("top", {
        "inner": {"workflow": {"name": "train_predict", "version": "1"}, "_hash_of_workflow_def": "sub",
                  "input": {"count": "c"}, "output": {"pred": "result"}},
    }, ["inner"], output={"result": FILE}, bind={"c": {"type": "int", "format": "int", "value": 3}})
    with pytest.raises(dbc.ParmaException):
        eo.parma2snakemake({"hash": "top"})


def test_register_external_run(store, monkeypatch):
    import component.run as run
    store["wf"] = _train_predict()
    runs = {}
    stored = []
    monkeypatch.setattr(db, "_run", runs)
    monkeypatch.setattr(db, "_data", {"d1": {"name": "pred"}})
    monkeypatch.setattr(db, "store_tables", lambda: stored.append(True))
    run_hash = run.register_external_run("wf", True, ["line 1", "line 2"], {"pred": "d1"}, "snakemake", "user-hash",
                                         run_name="run_snakefile_train_predict_1", executor_log=["sm 1"])
    entry = runs[run_hash]
    assert entry["name"] == "run_snakefile_train_predict_1"
    assert entry["_log_snakemake"] == ["sm 1"]
    assert entry["_hash_of_workflow"] == "wf"
    assert entry["_executor"] == "snakemake"
    assert entry["_log"] == ["line 1", "line 2"]
    assert entry["_channel_bindings"] == {"pred": "d1"}
    assert entry["_success"] is True
    assert entry["_version"] == 1
    assert entry["nodes"] == store["wf"]["nodes"]
    assert stored == [True]  # persisted
    default = runs[run.register_external_run("wf", False, [], {}, "snakemake", "user-hash")]
    assert default["name"] == "train_predict" and "_log_snakemake" not in default
    with pytest.raises(dbc.ParmaException):  # invalid run name
        run.register_external_run("wf", True, [], {}, "snakemake", "user-hash", run_name="no spaces")
    with pytest.raises(dbc.ParmaException):  # "builtin" is reserved for run.py
        run.register_external_run("wf", True, [], {}, "builtin", "user-hash")
    with pytest.raises(dbc.ParmaException):  # unknown data
        run.register_external_run("wf", True, [], {"pred": "unknown"}, "snakemake", "user-hash")
