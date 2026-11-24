import os
import copy
import re
import shlex
from python_on_whales import docker
import subprocess
import logging
import intern.dbc as dbc
import intern.helper as h
import intern.database as db
import intern.msg as msg
import component.data as d
import component.node as n
import component.workflow as wf


logger = logging.getLogger(__name__)
bash_on_linux = None
bash_on_windows = None
nix_on_linux = None


def init(bash_on_linux_config: str, bash_on_windows_config: str, nix_on_linux_config: str):
    global bash_on_linux, bash_on_windows, nix_on_linux
    bash_on_linux = bash_on_linux_config
    bash_on_windows = bash_on_windows_config
    nix_on_linux = nix_on_linux_config


def get_run_hash_by_referer(referer: dict) -> str:
    """
    Retrieves the hash of a run entry by using a referer.

    Args:
        referer (dict): Must have 'name' and 'version' properties, or a 'hash' property, but NOT both.
                A hash is for internal use only (e.g. by the frontend, hashes from lists); user inputs
                (definitions, referer files) are validated against the schema "name_version" before.

    Returns:
        str: The hash of the run entry object.

    Raises:
        Raises an error if the run entry is not found.
    """
    if "name" in referer and "version" in referer and not "hash" in referer:
        hash = h.opt_hash_by_key_value_and_version(db._run, referer["name"], referer["version"])
        dbc.assert_true(hash, {"msg": "NOT_FOUND", "kind": "run definition", "name": referer["name"]})
        return hash
    elif not "name" in referer and not "version" in referer and "hash" in referer:
        return db.get_hash_from_prefix(referer["hash"], table=db._run)
    dbc.raise_error({"msg": "NOT_FOUND", "kind": "run", "name": msg.referer2str(referer)})

def get_run_by_hash(hash: str) -> dict:
    """
    Retrieves a run entry by its hash.

    Args:
        hash (str): The hash of the run entry.

    Returns:
        dict: The run entry object.

    Raises:
        Raises an error if the run entry is not found.
    """
    run = db._run[hash]
    dbc.assert_true(
        run, {"msg": "NOT_FOUND", "kind": "run: hash", "name": hash}
    )
    return run

def get_all_runs() -> list:
    """
    Returns a list of all run entries known to the backend, each entry
    including its hash under the key '_hash'.

    Returns:
        list[dict]: All run objects.
    """
    return [dict(run, _hash=hash) for hash, run in db._run.items()]


def run_workflow(run_def: dict, channel_bindings: dict, logged_in_user: str) -> str:
    """
    Executes a workflow run based on the provided run definition and channel bindings (from a super workflow).

    Args:
        run_def (dict): The run definition, including workflow reference and run name.
        channel_bindings (dict): Bindings for workflow channels (input/output). May be empty (if, e.g. run by the user)
        logged_in_user (str): The user performing the operation.

    Returns:
        str: The hash of the stored run entry.
    """
    h.validate_user_input(run_def, "run_def")
    hash_of_workflow = wf.get_workflow_hash_by_referer(run_def["workflow"])
    workflow = db._workflow[hash_of_workflow]
    run = copy.deepcopy(workflow)
    workflow = {}
    run["name"] = run_def["name"]
    run["_hash_of_workflow"] = hash_of_workflow
    run["_executor"] = "builtin"
    _add_to_log(run, f"*** workflow {run['name']} started ***", log_message=True)
    h.check_that_node_channels_are_bound(wf.used_nodes(run["nodes"]), n.get_node_by_hash, wf.get_workflow_by_hash)

    result = _run_nodes_lazily(run, channel_bindings, logged_in_user)
    data_bindings = {}
    for channel, channel_bindung in channel_bindings.items():
        if channel_bindung["type"] == "file" or channel_bindung["type"] == "directory":
            data_bindings[channel] = channel_bindung["hash_of_data"]
    run["_channel_bindings"] = data_bindings
    number_new_data_entities = len(data_bindings)
    msg.log(logger.info, {"msg": "NUMBER_DATA_CREATED", "number": number_new_data_entities})
    if result:
        run["_success"] = True
        _add_to_log(run, f"*** workflow {run['name']} finished successfully ***", log_message=True)
    else:
        run["_success"] = False
        _add_to_log(run, f"*** workflow {run['name']} cancelled due to errors ***", log_message=True)
    hash_of_run = db.enrich_and_store_in_table(db._run, run, logged_in_user)
    if result:
        return hash_of_run
    else:
        details = f"*** workflow {run['name']} with hash {db.shrink_hash(hash_of_run)} cancelled due to errors ***"
        dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)


def register_external_run(workflow_hash: str, success: bool, log: list, channel_bindings: dict, executor: str,
                          logged_in_user: str, run_name: str = None, executor_log: list = None) -> str:
    """
    Stores the run record of a workflow executed by an external orchestrator (e.g. an exported Snakefile).
    The record is built like the one of run_workflow: a copy of the workflow with "name", "_hash_of_workflow",
    "_log", "_channel_bindings", "_success" and "_executor". The log of the orchestrator itself is stored as
    "_log_<executor>" (e.g. "_log_snakemake"). The tables are persisted immediately.

    Args:
        workflow_hash (str): The hash of the executed workflow.
        success (bool): Whether the run was successful.
        log (list[str]): The run log (in the style of run_workflow).
        channel_bindings (dict): channel -> hash of the data entry written to the channel.
        executor (str): The external orchestrator, e.g. "snakemake".
        logged_in_user (str): The user performing the operation.
        run_name (str): The name of the run. Default: the name of the workflow.
        executor_log (list[str]): The log of the orchestrator (e.g. the output of snakemake). Optional.

    Returns:
        str: The hash of the stored run entry.
    """
    workflow = wf.get_workflow_by_hash(workflow_hash)
    run_name = run_name or workflow["name"]
    dbc.assert_true(isinstance(run_name, str) and re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", run_name),
                    {"msg": "INVALID_NAME"})
    dbc.assert_true(isinstance(executor, str) and re.fullmatch(r"[a-z][a-z0-9_]*", executor) and executor != "builtin",
                    {"msg": "SYSTEM_ERROR", "details": f"invalid executor {executor!r}"})
    dbc.assert_true(isinstance(success, bool), {"msg": "SYSTEM_ERROR", "details": "\"success\" must be a bool"})
    for name, lines in (("log", log), ("executor_log", executor_log or [])):
        dbc.assert_true(isinstance(lines, list) and all(isinstance(line, str) for line in lines),
                        {"msg": "SYSTEM_ERROR", "details": f"\"{name}\" must be a list of strings"})
    dbc.assert_true(isinstance(channel_bindings, dict),
                    {"msg": "SYSTEM_ERROR", "details": "\"channel_bindings\" must be an object"})
    for channel, hash_of_data in channel_bindings.items():
        dbc.assert_true(isinstance(hash_of_data, str) and hash_of_data in db._data,
                        {"msg": "NOT_FOUND", "kind": f"data of channel {channel}", "name": str(hash_of_data)})
    run = copy.deepcopy(workflow)
    run["name"] = run_name
    run["_hash_of_workflow"] = workflow_hash
    run["_executor"] = executor
    run["_log"] = list(log)
    if executor_log is not None:
        run[f"_log_{executor}"] = list(executor_log)
    run["_channel_bindings"] = dict(channel_bindings)
    run["_success"] = success
    hash_of_run = db.enrich_and_store_in_table(db._run, run, logged_in_user)
    db.store_tables()
    return hash_of_run


def _run_nodes_lazily(run: dict, channel_bindings: dict, logged_in_user: str) -> bool:
    """
    Executes the nodes of a workflow run demand driven ("lazy"), because of if nodes: of an if node only
    the branch selected by the condition is executed, and nodes are only executed if their outputs are
    needed.

    The roots are the nodes that write a workflow output or whose outputs are read by no other node (they
    are executed in topological order). Before a node is executed, the nodes writing the channels it
    reads are executed. For an if node first the
    writer of the condition is executed, then the condition is evaluated, then the writers of the inputs
    of the selected branch, then the branch. Nodes never demanded are skipped (e.g. nodes whose outputs
    are only read by the branch not selected). Without if nodes all nodes are executed.

    Args:
        run (dict): The run entry (a copy of the workflow).
        channel_bindings (dict): Bindings for workflow channels. Outputs of executed nodes are added.
        logged_in_user (str): The user performing the operation.

    Returns:
        bool: True if all nodes executed were successful, False otherwise (execution stops at the first failure).
    """
    nodes = run["nodes"]
    order = run["_topological_order"]
    position = {name: index for index, name in enumerate(order)}
    writer_of = {channel: name for name, node in nodes.items() for channel in wf.node_output_channels(node)}
    channels_read = {channel for node in nodes.values() for channel in wf.node_input_channels(node)}
    state = {}  # node name -> True (executed successfully) | False (failed or being evaluated)

    def by_position(names) -> list:
        return sorted(set(names), key=position.get)

    def ensure_written(channels) -> bool:
        """executes the nodes writing the channels (not yet executed). Inputs and binds have no writer"""
        return all(evaluate(writer) for writer in by_position(writer_of[c] for c in channels if c in writer_of))

    def evaluate(node_name: str) -> bool:
        if node_name in state:
            return state[node_name]
        state[node_name] = False  # cycles are excluded when the workflow is stored
        node = nodes[node_name]
        if "if" in node:
            ok = ensure_written([node["if"]])
            if ok:
                condition = _condition_value(node_name, node["if"], run, channel_bindings)
                branch = "then" if condition else "else"
                used = node[branch].get("node") or node[branch].get("workflow")
                _add_to_log(run, f"if node \"{node_name}\": condition \"{node['if']}\" is {condition}, "
                                 f"the {branch} branch {used['name']}:{used['version']} is executed", log_message=True)
                ok = ensure_written(node[branch]["input"].values()) and \
                     _run_used_node(f"{node_name}_{branch}", node[branch], run, channel_bindings, logged_in_user)
        else:
            ok = ensure_written(node["input"].values()) and \
                 _run_used_node(node_name, node, run, channel_bindings, logged_in_user)
        state[node_name] = ok
        return ok

    roots = [name for name in order
             if any(channel in run["output"] or channel not in channels_read for channel in wf.node_output_channels(nodes[name]))
             or not wf.node_output_channels(nodes[name])]
    result = all(evaluate(root) for root in roots)
    if result:
        for node_name in order:
            if node_name not in state:
                _add_to_log(run, f"node: {node_name} skipped, its outputs are not needed (lazy evaluation of if nodes)", log_message=True)
    return result


def _run_used_node(node_name: str, node: dict, run: dict, channel_bindings: dict, logged_in_user: str) -> bool:
    """executes a node or sub workflow (a workflow node or the selected branch of an if node)"""
    _add_to_log(run, f"node: {node_name}", log_message=True)
    if "node" in node:  # a terminal node, a docker image
        return _run_terminal_node(node, run, channel_bindings, logged_in_user)
    return _run_workflow_node(node_name, node, run, channel_bindings, logged_in_user)  # a workflow embedded in another workflow


def _condition_value(node_name: str, channel: str, run: dict, channel_bindings: dict) -> bool:
    """the value of the condition channel of an if node: a bind (constant) or a binding passed to the workflow (e.g. an input)"""
    if channel in channel_bindings and "value" in channel_bindings[channel]:
        value = channel_bindings[channel]["value"]
    elif channel in run["bind"] and "value" in run["bind"][channel]:
        value = run["bind"][channel]["value"]
    else:
        details = f"if node \"{node_name}\": no value for the condition channel \"{channel}\""
        dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
    if not isinstance(value, bool):
        details = f"if node \"{node_name}\": the condition channel \"{channel}\" has the non bool value {value!r}"
        dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
    return value


def _run_terminal_node(terminal_node: dict, run: dict, dynamic_channel_bindings: dict, logged_in_user: str) -> bool:
    """
    Executes a terminal node (Docker image) in the workflow.

    Args:
        terminal_node (dict): The terminal node definition.
        run (dict): The current run object.
        dynamic_channel_bindings (dict): Bindings for workflow channels.
        logged_in_user (str): The user performing the operation.

    Returns:
        bool: True if execution was successful, False otherwise.
    """
    node_hash = terminal_node["_hash_of_node_def"]
    node_def = n.get_node_by_hash(node_hash)
    mounts = []
    envvars = []
    cli_args = []
    output_channel_to_path = {}

    for channel_output_name, channel_rename in terminal_node["input"].items():
        node_channel = node_def["input"][channel_output_name]
        if channel_rename in run["input"] or channel_rename in run["connect"]:
            if channel_rename not in dynamic_channel_bindings:
                details = f"channel {channel_rename} read, but not available"
                dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
            else:
                dynamic_binding = dynamic_channel_bindings[channel_rename]
                if dynamic_binding["type"] == "file" or dynamic_binding["type"] == "directory":
                    if "path_in_container" in node_channel:
                        path_inside = node_channel["path_in_container"]
                        path_outside = d.get_path_by_hash(dynamic_binding["hash_of_data"], for_mounting=True)
                        mounts.append((path_outside, path_inside))
                    elif "environment_var_in_container" in node_channel:
                        envvar_name = node_channel["environment_var_in_container"]
                        path_outside = d.get_path_by_hash(dynamic_binding["hash_of_data"])
                        envvars.append((envvar_name, path_outside))
                    else:
                        details = f"invalid node declaration \"{str(dynamic_binding)}\""
                        dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
                elif dynamic_binding["type"] == "environment_var" or dynamic_binding["type"] in n.CONSTANT_TYPES:
                    value_as_str = h.value_to_str(dynamic_binding["value"], dynamic_binding["type"])
                    _pass_value(channel_output_name, node_channel, value_as_str, envvars, cli_args)
                else:
                    details = f"invalid input binding \"{str(dynamic_binding)}\""
                    dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
        elif channel_rename in run["bind"]:
            dynamic_binding = run["bind"][channel_rename]
            if dynamic_binding["type"] == "file" or dynamic_binding["type"] == "directory":
                hash_of_data = d.get_data_hash_by_referer(dynamic_binding["data"])
                if "path_in_container" in node_channel:
                    path_inside = node_channel["path_in_container"]
                    path_outside = d.get_path_by_hash(hash_of_data, for_mounting=True)
                    mounts.append((path_outside, path_inside))
                elif "environment_var_in_container" in node_channel:
                    envvar_name = node_channel["environment_var_in_container"]
                    path_outside = d.get_path_by_hash(hash_of_data)
                    envvars.append((envvar_name, path_outside))
                else:
                    details = f"invalid node declaration \"{str(dynamic_binding)}\""
                    dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
            elif dynamic_binding["type"] == "environment_var":
                _pass_value(channel_output_name, node_channel, dynamic_binding["environment_var_value"], envvars, cli_args)
            elif dynamic_binding["type"] in n.CONSTANT_TYPES:
                value_as_str = h.value_to_str(dynamic_binding["value"], dynamic_binding["type"])
                _pass_value(channel_output_name, node_channel, value_as_str, envvars, cli_args)
            else:
                details = f"invalid bind decl \"{str(dynamic_binding)}\""
                dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
        else:
            dbc.raise_error({"msg": "SYSTEM_ERROR", "details": f"channel {channel_output_name} invalid"}, user_error=False)

    temp_dirs = set()
    for channel_output_name, channel_rename in terminal_node["output"].items():
        binding_defined_in_run = None
        if channel_rename in run["output"]:
            binding_defined_in_run = run["output"][channel_rename]
        elif channel_rename in run["connect"]:
            binding_defined_in_run = run["connect"][channel_rename]
        else:
            details = f"invalid channel \"{str(channel_rename)}\""
            dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)

        node_channel = node_def["output"][channel_output_name]

        path_inside = node_channel.get("path_in_container")
        envvar_name = node_channel.get("environment_var_in_container")
        platform_storage = not "storage" in binding_defined_in_run or binding_defined_in_run["storage"] == "platform"
        if platform_storage and binding_defined_in_run["type"] == "file":
            (temp_dir, temp_dir_for_mount) = db.create_a_temp_directory()
            temp_dirs.add(temp_dir)
            path_outside = os.path.join(temp_dir, channel_rename)
            _prepare_output_file(path_outside)
            if "_image_id" in node_def:
                path_outside_for_mount = f"{temp_dir_for_mount}/{channel_rename}"
                mounts.append((path_outside_for_mount, path_inside))
            elif "_bash_id" in node_def:
                envvars.append((envvar_name, path_outside))
            elif "nix" in node_def:
                envvars.append((envvar_name, path_outside))
            else:
                details = f"node is neither for docker nor for bash"
                dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
        elif not platform_storage and binding_defined_in_run["type"] == "file":
            path_outside = binding_defined_in_run["user_path"]
            path_outside = os.path.abspath(path_outside)
            if "_image_id" in node_def:
                _prepare_output_file(path_outside)
                mounts.append((path_outside, path_inside))
            elif "_bash_id" in node_def:
                envvars.append((envvar_name, path_outside))
            elif "nix" in node_def:
                envvars.append((envvar_name, path_outside))
            else:
                details = f"node is neither for docker nor for bash"
                dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
        elif not platform_storage and binding_defined_in_run["type"] == "directory":
            path_outside = binding_defined_in_run["user_path"]
            path_outside = os.path.abspath(path_outside)
            _prepare_output_directory(path_outside)
            if "_image_id" in node_def:
                mounts.append((path_outside, path_inside))
            elif "_bash_id" in node_def:
                envvars.append((envvar_name, path_outside))
            elif "nix" in node_def:
                envvars.append((envvar_name, path_outside))
            else:
                details = f"node is neither for docker nor for bash"
                dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
        else:
            details = f"invalid combination of \"storage\" and \"path\" for channel \"{str(channel_rename)}\" (pre docker)"
            dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
        output_channel_to_path[channel_rename] = {"path_outside": path_outside, "binding_defined_in_run": binding_defined_in_run, "node_channel": node_channel}

    if "_image_id" in node_def:
        result = _run_docker_as_subprocess(run, node_def["_image_id"], mounts, envvars, cli_args)
    elif "_bash_id" in node_def:
        result = _run_bash(run, node_def["_bash_id"], envvars, cli_args)
    elif "nix" in node_def:
        uri = node_def.get("nix",{}).get("uri", None)
        hash = node_def.get("nix",{}).get("hash", None)
        result = _run_nix(run, uri, hash, envvars)
    else:
        details = "node is neither image nor bash"
        dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)

    for channel_output_name, channel_output_def in output_channel_to_path.items():
        binding_defined_in_run = channel_output_def["binding_defined_in_run"]
        node_channel = channel_output_def["node_channel"]
        path_outside = channel_output_def["path_outside"]
        platform_storage = not "storage" in binding_defined_in_run or binding_defined_in_run["storage"] == "platform"
        if platform_storage and binding_defined_in_run["type"] == "file":
            hash_of_data = d.add_data({"name": channel_output_name, "type": "file", "storage": "platform", "hash": "true", "format": "any",
                                       "user_path": path_outside}, logged_in_user, ignore_errors=True, delete_user_path=True)
        elif not platform_storage:
            hash_of_data = d.add_data({"name": channel_output_name, "type": binding_defined_in_run["type"], "storage": "extern", "hash": "false", "format": "any",
                                       "user_path": path_outside}, logged_in_user, ignore_errors=True, delete_user_path=False)
        else:
            details = f"invalid combination of \"storeage\" and \"path\" for channel \"{str(channel_rename)}\" (post docker)"
            dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
        if hash_of_data:
            binding_for_next_steps = {"type": binding_defined_in_run["type"], "format": "any", "hash_of_data": hash_of_data}
            dynamic_channel_bindings[channel_output_name] = binding_for_next_steps
        else:
            _add_to_log(run, f'output channel "{channel_output_name}" was not generated and is not saved')
    _add_to_log(run, f"run finished. Success: {result}")
    return result

def _pass_value(channel_name: str, node_channel: dict, value_as_str: str, envvars: list, cli_args: list) -> None:
    """
    Passes a value (environment var or constant) to a node, either as environment variable or as
    command line parameter, as declared by the node channel.
    """
    if "environment_var_in_container" in node_channel:
        envvars.append((node_channel["environment_var_in_container"], value_as_str))
    elif "command_line_parameter" in node_channel:
        cli_args.extend([node_channel["command_line_parameter"], value_as_str])
    else:
        details = f"channel \"{channel_name}\" declares neither environment var nor command line parameter"
        dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)


def _binding_of_bind(channel: str, bind: dict) -> dict:
    """
    The dynamic binding passed to a sub workflow for a bind of the calling workflow. It has the form
    expected for channels of the input section (see _run_terminal_node and _condition_value):
    data -> "hash_of_data", environment variables and constants -> "value".
    """
    binding = {"type": bind["type"], "format": bind.get("format", "any")}
    if bind["type"] == "file" or bind["type"] == "directory":
        binding["hash_of_data"] = d.get_data_hash_by_referer(bind["data"])
    elif bind["type"] == "environment_var":
        binding["value"] = bind["environment_var_value"]
    elif bind["type"] in n.CONSTANT_TYPES:
        binding["value"] = bind["value"]
    else:
        details = f"invalid bind decl \"{channel}\": {str(bind)}"
        dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
    return binding


def _run_workflow_node(workflow_name: str, workflow_node: dict, run: dict, super_bindings: dict, logged_in_user: str) -> bool:
    """
    Executes a sub-workflow node within a workflow.

    Args:
        workflow_name (str): Name of the sub-workflow.
        workflow_node (dict): The sub-workflow node definition.
        run (dict): The current run object.
        super_bindings (dict): Bindings for parent workflow channels.
        logged_in_user (str): The user performing the operation.

    Returns:
        bool: True if execution was successful, False otherwise.
    """
    sub_bindings = {}

    for channel_name, channel_rename in workflow_node["input"].items():
        if channel_rename in run["input"] or channel_rename in run["connect"]:
            if channel_rename in super_bindings:
                sub_bindings[channel_name] = super_bindings[channel_rename]
            else:
                details = f"channel {channel_rename} read, but not available"
                dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
        elif channel_rename in run["bind"]:
            sub_bindings[channel_name] = _binding_of_bind(channel_rename, run["bind"][channel_rename])
        else:
            dbc.raise_error({"msg": "SYSTEM_ERROR", "details": f"no binding for channel {channel_rename}"}, user_error=False)

    sub_workflow_run_hash = run_workflow({"name": workflow_name, "workflow": workflow_node["workflow"]}, sub_bindings, logged_in_user)
    sub_workflow_run = get_run_by_hash(sub_workflow_run_hash)
    result = sub_workflow_run["_success"]

    for channel_name, channel_rename in workflow_node["output"].items():
        if channel_rename in super_bindings:
            details = f"output channel {channel_rename} written twice"
            dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
        else:
            sub_binding = sub_bindings[channel_name]
            super_bindings[channel_rename] = sub_binding

    shrinked_hash = db.shrink_hash(sub_workflow_run_hash)
    _add_to_log(run, f"sub workflow \"{workflow_name}\" finished. Result: {result}, hash: {shrinked_hash}")
    return result

def _run_docker_with_whales(run: dict, image_name: str, mounts: list) -> None:
    """
    Runs a Docker image with several mounts.
    UNUSED, but kept for reference. Mounts are not working with this method (???).

    Args:
        run (dict): The run entry.
        image_name (str): The name of the Docker image to run.
        mounts (list of tuples): A list of mounts, where each tuple contains (host_path, container_path).
    """
    volumes = {
        host_path: {"bind": container_path} for host_path, container_path in mounts
    }
    docker.run(image_name, volumes=volumes)

def _run_docker_as_subprocess(run: dict, image_name: str, mounts: list, envvars: list, cli_args: list = None) -> bool:
    """
    Runs a Docker image as subprocess.

    Args:
        run (dict): The run entry.
        image_name (str): The name of the Docker image to run.
        mounts (list of tuples): A list of mounts, where each tuple contains (host_path, container_path).
        envvars (list of tuples): A list of bindings of environment var values to environment vars
        cli_args (list of str): Command line arguments appended after the image name

    Returns:
        bool: True if the command was successful, False otherwise.
    """
    command = ["docker", "run", "--rm"]
    for host_path, container_path in mounts:
        command.extend(["-v", f"{host_path}:{container_path}"])
    for env_name, env_val in envvars:
        command.extend(["-e", f"{env_name}={env_val}"])
    command.append(image_name)
    command.extend(cli_args or [])

    command_as_string = " ".join(command)
    _add_to_log(
        run, f"Running command: {command_as_string}"
    )  # Debugging: Print the constructed command

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        logging = result.stdout.strip()
        if logging and logging != "":
            _add_to_log(run, f"stdout: {logging}")
        logging = result.stderr.strip()
        if logging and logging != "":
            _add_to_log(run, f"stderr: {logging}")
        return True
    except subprocess.CalledProcessError as e:
        logging = e.stdout
        if logging and logging != "":
            _add_to_log(run, f"stdout: {logging}")
        logging = e.stderr
        if logging and logging != "":
            _add_to_log(run, f"stderr: {logging}")
        details = f"Error: Docker run failed with return code {e.returncode}"
        _add_to_log(run, details)
        return False

def _run_bash(run, bash_id, envvars, cli_args=None):
    bash_commands = []
    for env_name, env_val in envvars:
        bash_commands.append(f"{env_name}=\"{env_val}\"")
    path_bash_script = d.get_path_by_hash(bash_id).replace('\\','/')
    bash_commands.append(path_bash_script)
    bash_commands.extend(shlex.quote(arg) for arg in (cli_args or []))
    bash_command_as_string = " ".join(bash_commands)
    _add_to_log(
        run, f"Running bash command: {bash_command_as_string}"
    )  # Debugging: Print the constructed command

    try:
        if h.WINDOWS:
            details = "Error: currently no bash run on windows" # TODO: add bash run on windows if git bash is installed
            _add_to_log(run, details)
            return False
    
        bash_exe = bash_on_windows if h.WINDOWS else bash_on_linux
        result = subprocess.run([bash_exe, "-c", bash_command_as_string], capture_output=True, text=True, check=True)
        logging = result.stdout.strip()
        if logging and logging != "":
            _add_to_log(run, f"stdout: {logging}")
        logging = result.stderr.strip()
        if logging and logging != "":
            _add_to_log(run, f"stderr: {logging}")
        return True
    except subprocess.CalledProcessError as e:
        logging = e.stdout
        if logging and logging != "":
            _add_to_log(run, f"stdout: {logging}")
        logging = e.stderr
        if logging and logging != "":
            _add_to_log(run, f"stderr: {logging}")
        details = f"Error: bash run failed with return code {e.returncode}"
        _add_to_log(run, details)
        return False
    except Exception as e:
        details = f"Error: bash run failed with general exception {e}"
        _add_to_log(run, details)
        return False


def _run_nix(run, uri, hash, envvars):
    bash_commands = []
    for env_name, env_val in envvars:
        bash_commands.append(f"{env_name}=\"{env_val}\"")
    bash_commands.append(nix_on_linux)
    bash_commands.append('""' if uri == None else uri)
    bash_commands.append('""' if hash == None else hash)
    bash_command_as_string = " ".join(bash_commands)
    _add_to_log(
        run, f"Running nix command: {bash_command_as_string}"
    )  # Debugging: Print the constructed command

    try:
        if h.WINDOWS:
            details = "Error: no nix run on windows"
            _add_to_log(run, details)
            return False
    
        result = subprocess.run([bash_on_linux, "-c", bash_command_as_string], capture_output=True, text=True, check=True)
        logging = result.stdout.strip()
        if logging and logging != "":
            _add_to_log(run, f"stdout: {logging}")
        logging = result.stderr.strip()
        if logging and logging != "":
            _add_to_log(run, f"stderr: {logging}")
        return True
    except subprocess.CalledProcessError as e:
        logging = e.stdout
        if logging and logging != "":
            _add_to_log(run, f"stdout: {logging}")
        logging = e.stderr
        if logging and logging != "":
            _add_to_log(run, f"stderr: {logging}")
        details = f"Error: nix run failed with return code {e.returncode}"
        _add_to_log(run, details)
        return False
    except Exception as e:
        details = f"Error: nix run failed with general exception {e}"
        _add_to_log(run, details)
        return False
    

def _prepare_output_file(file_path: str) -> None:
    """
    Creates an empty file. Sets it read/write.

    Args:
        file_path (str): The path of the file to prepare.
    """
    try:
        if not os.path.exists(file_path):
            with open(file_path, "w") as f:
                pass  # Create an empty file
        h.set_file_writable(file_path)
    except subprocess.CalledProcessError as e:
        details = f"Error: Failed to prepare output file {file_path} with return code {e.returncode}"
        dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)

def _prepare_output_directory(path: str) -> None:
    """
    Creates a directory if it does not exist.

    Args:
        path (str): The directory path to create.
    """
    if not os.path.exists(path):
        os.makedirs(path)

def _add_to_log(run: dict, message: str, log_message: bool = True) -> None:
    """
    Adds a message to the log of a run entry.

    Args:
        run (dict): The run entry.
        message (str): The message to add to the log.
        print_message (bool): If True, also log the message.
    """
    if "_log" not in run:
        run["_log"] = []
    run["_log"].append(message)
    if log_message:
        logger.info(message)
