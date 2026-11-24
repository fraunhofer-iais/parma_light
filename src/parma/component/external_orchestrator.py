"""
Export of PARMA workflows to external orchestrators. Currently only Snakemake is supported.

parma2snakemake generates the text of a Snakefile that executes a stored workflow like run.py does:
- a terminal node (docker image) becomes a rule, that calls "docker run" (Snakemake's "container:" directive
  uses Apptainer, thus docker is called from a "run:" block. It is python, not a shell command, thus it works on
  Linux and Windows, where Snakemake uses cmd.exe as shell)
- a sub workflow is inlined, its rule and channel names are prefixed by "<node name>__"
- an if node becomes a python "if" in the Snakefile. The condition is evaluated when the Snakefile is parsed. This
  is possible, because the condition channel is always a bind or a workflow input, never computed by a node
- file and directory channels become paths, environment vars and constants are passed by "-e" or as command line
  parameters as declared by the node
- workflow inputs are taken from the Snakemake config (e.g. --config name=value)
- binds of data entities are resolved to their paths in the PARMA datastore. The Snakefile can only be used on
  a machine with the same datastore

Like run.py, a run of the Snakefile leaves its traces in PARMA. As Snakemake runs in a process of its own and the
backend keeps its tables in memory, everything is done by the REST API of the backend (environment variables
PARMA_URL, PARMA_USER and PARMA_PASSWORD, as for curl.sh; the Snakefile stops if one is missing. If the backend
runs the Snakefile (run_snakefile), it sets PARMA_TOKEN, the session token of the caller, instead of user and password):
- after a rule has run, its outputs are stored as data (name: the channel name, as run.py does)
- at the end (success or error) a run record with the run log and the channel bindings is stored and persisted.
  Its "_executor" is "snakemake", the log of snakemake itself is stored as "_log_snakemake". Other than run.py,
  sub workflows get no run records of their own: their nodes are part of the one run record, with prefixed names

Not supported:
- bash and nix nodes (an error is raised)
"""
import importlib.util
import logging
import os
import re
import shutil
import subprocess
import sys
import intern.dbc as dbc
import intern.database as db
import intern.helper as h
import component.data as d
import component.node as n
import component.workflow as wf


logger = logging.getLogger(__name__)

SEPARATOR = "__"
OUTPUT_LINES_RETURNED = 50  # the last lines of the Snakemake output returned by run_snakefile
_RUN_STORED = re.compile(r"^PARMA run (?P<name>.+):(?P<version>\d+) stored, hash (?P<hash>[0-9a-f]+)$")
INDENT = "    "
RECORD_DIR = ".parma"  # sub directory of the work dir for the log and bindings of the executed rules

_SNAKEFILE_HELPERS = '''
import json
import os
import shlex
import shutil
import subprocess

import requests


# PARMA_TOKEN (a session token, set if the backend runs the Snakefile) replaces PARMA_USER and PARMA_PASSWORD
for _parma_var in ("PARMA_URL",) + (() if os.environ.get("PARMA_TOKEN") else ("PARMA_USER", "PARMA_PASSWORD")):
    if not os.environ.get(_parma_var):
        raise ValueError(f"environment variable {_parma_var} is not set. The outputs and the run are stored in "
                         "PARMA, set PARMA_URL (e.g. http://localhost:8080), PARMA_USER and PARMA_PASSWORD")
PARMA_URL = os.environ["PARMA_URL"].rstrip("/")


def parma_str(value):
    """a constant as string passed to a node (like value_to_str in PARMA's helper.py)"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)) or value is None:
        return json.dumps(value)
    return str(value)


def parma_bool(value):
    """the value of the condition channel of an if node"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise ValueError(f"the condition of an if node has the non bool value {value!r}")


def _parma_post(route, token=None, **kwargs):
    """a request to the PARMA backend. Raises an error if it fails"""
    headers = {"X-Auth-Token": token} if token else {}
    response = requests.post(PARMA_URL + route, headers=headers, timeout=600, **kwargs)
    response.raise_for_status()
    result = response.json()
    if not result.get("success"):
        raise RuntimeError(f"PARMA request {route} failed: {result.get('error') or result.get('exception')}")
    return result


class _ParmaSession:
    """login and logout. A session per use, thus usable from parallel jobs. A given PARMA_TOKEN is used as is"""
    def __enter__(self):
        self.given_token = os.environ.get("PARMA_TOKEN")
        if self.given_token:
            return self.given_token
        credentials = {"name": os.environ["PARMA_USER"], "password": os.environ["PARMA_PASSWORD"]}
        self.token = _parma_post("/user/login", json=credentials)["token"]
        return self.token

    def __exit__(self, *exception):
        if self.given_token:
            return
        try:
            _parma_post("/user/logout", self.token, json={})
        except Exception:
            pass


def _parma_record_path(rule_name):
    return os.path.join(PARMA_WORK_DIR, PARMA_RECORD_DIR, rule_name + ".json")


def _parma_store_output(token, path, data_name, storage, data_type):
    """stores an output as data like run.py does and returns the hash of the data"""
    if storage == "extern":
        definition = {"name": data_name, "type": data_type, "storage": "extern", "hash": "false", "format": "any",
                      "user_path": os.path.abspath(path)}
        return _parma_post("/data/upload", token, json={"content": json.dumps(definition)})["hash"]
    with open(path, "rb") as f:
        return _parma_post("/data/upload-file", token, files={"file": (os.path.basename(path), f)},
                           data={"name": data_name})["hash"]


def parma_docker_run(rule_name, node_name, image, mounts=(), envvars=(), cli_args=(), output_files=(),
                     output_dirs=(), done_marker=None, register=()):
    """
    runs a docker image (without a shell, thus on Linux and Windows) and stores its outputs as data in PARMA.
    Output files are created before, as docker would create directories for missing mount sources.
    The log and the bindings (channel -> hash of data) are written to a record file, read at the end of the run.
    register: (path, data name, storage, type, channel of the run) for every output
    """
    log = [f"node: {node_name}"]
    bindings = {}
    try:
        for path in output_dirs:
            os.makedirs(path, exist_ok=True)
        for path in output_files:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            open(path, "a").close()
        command = ["docker", "run", "--rm"]
        for host_path, container_path in mounts:
            command += ["-v", os.path.abspath(host_path) + ":" + container_path]
        for name, value in envvars:
            command += ["-e", name + "=" + value]
        command.append(image)
        command += list(cli_args)
        log.append("Running command: " + " ".join(shlex.quote(part) for part in command))
        print(log[-1], flush=True)
        result = subprocess.run(command, capture_output=True, text=True)
        for stream, text in (("stdout", result.stdout), ("stderr", result.stderr)):
            if text and text.strip():
                log.append(f"{stream}: {text.strip()}")
                print(log[-1], flush=True)
        success = result.returncode == 0
        if not success:
            log.append(f"Error: Docker run failed with return code {result.returncode}")
        # like run.py: the outputs are stored, even if the run failed
        with _ParmaSession() as token:
            for path, data_name, storage, data_type, channel in register:
                if not os.path.exists(path):
                    log.append(f'output channel "{data_name}" was not generated and is not saved')
                    continue
                bindings[channel] = _parma_store_output(token, path, data_name, storage, data_type)
        if success and done_marker:
            os.makedirs(os.path.dirname(done_marker), exist_ok=True)
            open(done_marker, "a").close()
        log.append(f"run finished. Success: {success}")
    except Exception as e:
        success = False
        log.append(f"Error: {e}")
        log.append("run finished. Success: False")
    finally:
        os.makedirs(os.path.dirname(_parma_record_path(rule_name)), exist_ok=True)
        with open(_parma_record_path(rule_name), "w", encoding="utf-8") as f:
            json.dump({"log": log, "bindings": bindings}, f)
    if not success:
        raise RuntimeError(f"node {node_name} failed, see the log above")


def parma_register_run(success, snakemake_log_files):
    """stores the run record (log and channel bindings of all executed rules, the snakemake log) in PARMA"""
    log = [f"*** workflow {PARMA_WORKFLOW_NAME} started ***"] + PARMA_LOG_PREAMBLE
    bindings = {}
    for rule_name in PARMA_RULE_ORDER:
        if os.path.exists(_parma_record_path(rule_name)):
            with open(_parma_record_path(rule_name), encoding="utf-8") as f:
                record = json.load(f)
            log += record["log"]
            bindings.update(record["bindings"])
    if success:
        log.append(f"*** workflow {PARMA_WORKFLOW_NAME} finished successfully ***")
    else:
        log.append(f"*** workflow {PARMA_WORKFLOW_NAME} cancelled due to errors ***")
    snakemake_log = []
    # depending on the snakemake version a file name or a list of file names
    log_files = [snakemake_log_files] if isinstance(snakemake_log_files, str) else list(snakemake_log_files or [])
    for log_file in log_files:
        if os.path.exists(log_file):
            with open(log_file, encoding="utf-8", errors="replace") as f:
                snakemake_log += f.read().splitlines()
    run = {"workflow": {"hash": PARMA_WORKFLOW_HASH}, "name": PARMA_RUN_NAME, "success": success, "log": log,
           "channel_bindings": bindings, "executor": "snakemake", "executor_log": snakemake_log}
    with _ParmaSession() as token:
        result = _parma_post("/run/register", token, json=run)
    print(f"PARMA run {result['name']}:{result['version']} stored, hash {result['hash']}", flush=True)


PARMA_TARGETS = []
PARMA_LOG_PREAMBLE = []


onstart:
    # records of earlier runs must not be part of this run
    shutil.rmtree(os.path.join(PARMA_WORK_DIR, PARMA_RECORD_DIR), ignore_errors=True)

# "log" is the file containing the log of snakemake
onsuccess:
    parma_register_run(True, log)

onerror:
    parma_register_run(False, log)


rule all:
    input:
        lambda wildcards: PARMA_TARGETS
'''


def parma2snakemake(workflow_referer: dict, work_dir: str = "parma_work", run_name: str = None) -> str:
    """
    Generates a Snakefile, that executes a workflow (see the module documentation for the mapping and its limits).

    Args:
        workflow_referer (dict): Referer of the workflow ('name' and 'version', or 'hash').
        work_dir (str): Directory (relative to the Snakemake working directory) for outputs with platform storage
            and intermediate data.
        run_name (str): Name of the run records stored by the Snakefile. Default: the name of the workflow.

    Returns:
        str: The text of the Snakefile.

    Raises:
        Raises an error if the workflow is not found or uses bash or nix nodes.
    """
    hash_of_workflow = wf.get_workflow_hash_by_referer(workflow_referer)
    workflow = wf.get_workflow_by_hash(hash_of_workflow)
    h.check_that_node_channels_are_bound(wf.used_nodes(workflow["nodes"]), n.get_node_by_hash, wf.get_workflow_by_hash)

    sources = {}
    for channel, channel_def in workflow["input"].items():
        sources[channel] = _config_source(channel, channel_def)
    for channel, channel_def in workflow["output"].items():
        sources[channel] = _output_source(channel_def, f"{work_dir}/{channel}")

    lines = []
    for channel in workflow["output"]:
        lines.append(f"PARMA_TARGETS.append({sources[channel]['expr']})")
    rule_order = []
    _emit_workflow(workflow, "", sources, work_dir, lines, rule_order, depth=0)

    header = [
        f"# Snakefile generated by PARMA-light from workflow {workflow['name']} "
        f"(version {workflow.get('_version', '?')}, hash {hash_of_workflow})",
        "# Outputs and the run are stored in PARMA. Set the environment variables PARMA_URL, PARMA_USER, PARMA_PASSWORD",
        "# Run with: snakemake --cores 1" + "".join(f" --config {c}=..." for c in workflow["input"]),
    ]
    for channel, channel_def in workflow["input"].items():
        header.append(f"#   config \"{channel}\": {channel_def['type']}" +
                      (" (a path)" if channel_def["type"] in ("file", "directory") else ""))
    constants = [
        "",
        f"PARMA_WORKFLOW_HASH = {hash_of_workflow!r}",
        f"PARMA_WORKFLOW_NAME = {workflow['name']!r}",
        f"PARMA_RUN_NAME = {(run_name or workflow['name'])!r}",
        f"PARMA_WORK_DIR = {work_dir!r}",
        f"PARMA_RECORD_DIR = {RECORD_DIR!r}",
        f"PARMA_RULE_ORDER = {rule_order!r}",
    ]
    return "\n".join(header + constants) + "\n" + _SNAKEFILE_HELPERS + "\n\n" + "\n".join(lines) + "\n"


def run_snakefile(snakefile_referer: dict, cores: int, parma_url: str, token: str) -> dict:
    """
    Runs a Snakefile stored as data with Snakemake (of the python environment of the backend) in a temporary
    directory, that is removed afterwards. The Snakefile stores the outputs and the run record by the REST API
    of the backend at parma_url, using the session token of the caller. Returns when Snakemake has finished.

    Args:
        snakefile_referer (dict): Referer ('name' and 'version') of the data entry containing the Snakefile.
        cores (int): Number of cores Snakemake may use (--cores).
        parma_url (str): URL of this backend, as seen from the backend machine.
        token (str): Session token of the calling user.

    Returns:
        dict: "success", "exit_code" of Snakemake, "run" (hash, name, version of the stored run record or None)
            and "output" (the last lines of the Snakemake output).
    """
    dbc.assert_true(not h.RUNNING_IN_CONTAINER,
                    {"msg": "SYSTEM_ERROR", "details": "running a Snakefile is not supported if PARMA runs in a container"})
    dbc.assert_true(importlib.util.find_spec("snakemake") is not None,
                    {"msg": "SYSTEM_ERROR", "details": "snakemake is not installed in the python environment of the backend"})
    snakefile_path = d.get_path_by_hash(d.get_data_hash_by_referer(snakefile_referer))
    work_dir, _ = db.create_a_temp_directory()
    env = dict(os.environ, PARMA_URL=parma_url, PARMA_TOKEN=token)
    env.pop("PARMA_USER", None)
    env.pop("PARMA_PASSWORD", None)
    command = [sys.executable, "-m", "snakemake", "--cores", str(cores), "--snakefile", "Snakefile"]
    msg_text = f"running Snakefile {snakefile_referer['name']}:{snakefile_referer['version']} with {cores} core(s)"
    logger.info(msg_text)
    try:
        shutil.copyfile(snakefile_path, os.path.join(work_dir, "Snakefile"))
        completed = subprocess.run(command, cwd=work_dir, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    output = completed.stdout.splitlines()
    run = None
    for line in output:
        match = _RUN_STORED.match(line.strip())
        if match:
            run = {"hash": match["hash"], "name": match["name"], "version": int(match["version"])}
    logger.info(f"Snakemake finished with exit code {completed.returncode}, run: {run}")
    return {"success": completed.returncode == 0 and run is not None, "exit_code": completed.returncode,
            "run": run, "output": output[-OUTPUT_LINES_RETURNED:]}


def _config_source(channel: str, channel_def: dict) -> dict:
    """the source of a workflow input: a value of the Snakemake config"""
    return {"kind": _kind(channel_def), "expr": f"config[{channel!r}]"}


def _output_source(channel_def: dict, platform_path: str) -> dict:
    """the source of a channel written by a node: a path in the work dir or the user path for extern storage"""
    storage = channel_def.get("storage", "platform")
    path = channel_def["user_path"] if storage == "extern" else platform_path
    return {"kind": _kind(channel_def), "expr": repr(path.replace("\\", "/")), "storage": storage}


def _bind_source(channel: str, bind: dict) -> dict:
    """the source of a bind: a path into the datastore or a constant value"""
    if bind["type"] in ("file", "directory"):
        path = d.get_path_by_hash(d.get_data_hash_by_referer(bind["data"]))
        return {"kind": bind["type"], "expr": repr(path.replace("\\", "/"))}
    elif bind["type"] == "environment_var":
        return {"kind": "value", "expr": repr(bind["environment_var_value"])}
    elif bind["type"] in n.CONSTANT_TYPES:
        return {"kind": "value", "expr": repr(bind["value"])}
    dbc.raise_error({"msg": "SYSTEM_ERROR", "details": f"invalid bind decl \"{channel}\": {str(bind)}"}, user_error=False)


def _kind(channel_def: dict) -> str:
    return channel_def["type"] if channel_def["type"] in ("file", "directory") else "value"


def _emit_workflow(workflow: dict, prefix: str, sources: dict, work_dir: str, lines: list, rule_order: list,
                   depth: int) -> None:
    """
    Emits the rules of a workflow. sources maps the input and output channels of the workflow to their sources
    (dicts with "kind" (file, directory, value), "expr" (a python expression in the Snakefile) and for outputs
    "storage"). Binds and connects are added here.
    """
    sources = dict(sources)
    for channel, bind in workflow["bind"].items():
        sources[channel] = _bind_source(channel, bind)
    for channel, channel_def in workflow["connect"].items():
        sources[channel] = _output_source(channel_def, f"{work_dir}/{prefix}{channel}")

    nodes = workflow["nodes"]
    channels_read = {channel for node in nodes.values() for channel in wf.node_input_channels(node)}
    for node_name in workflow["_topological_order"]:
        node = nodes[node_name]
        # connects read by no node are targets (run.py executes the writing nodes, too)
        unread = [c for c in wf.node_output_channels(node) if c in workflow["connect"] and c not in channels_read]
        if "if" in node:
            condition = sources[node["if"]]["expr"]
            for branch, value in (("then", True), ("else", False)):
                lines.append(INDENT * depth + (f"if parma_bool({condition}):" if value else "else:"))
                used = node[branch].get("node") or node[branch].get("workflow")
                message = (f"if node \"{prefix}{node_name}\": condition \"{node['if']}\" is {value}, "
                           f"the {branch} branch {used['name']}:{used['version']} is executed")
                lines.append(INDENT * (depth + 1) + f"PARMA_LOG_PREAMBLE.append({message!r})")
                _emit_used_node(f"{prefix}{node_name}_{branch}", prefix, node[branch], sources, unread, work_dir,
                                lines, rule_order, depth + 1)
        else:
            _emit_used_node(f"{prefix}{node_name}", prefix, node, sources, unread, work_dir, lines, rule_order, depth)


def _emit_used_node(name: str, prefix: str, node: dict, sources: dict, unread: list, work_dir: str, lines: list,
                    rule_order: list, depth: int) -> None:
    """emits a terminal node or a sub workflow (a workflow node or a branch of an if node)"""
    for channel in unread:
        lines.append(INDENT * depth + f"PARMA_TARGETS.append({sources[channel]['expr']})")
    if "node" in node:
        _emit_terminal_rule(name, prefix, node, sources, work_dir, lines, rule_order, depth)
        return
    sub_workflow = wf.get_workflow_by_hash(node["_hash_of_workflow_def"])
    sub_sources = {}
    for sub_channel, channel in list(node["input"].items()) + list(node["output"].items()):
        sub_sources[sub_channel] = sources[channel]
    _emit_workflow(sub_workflow, name + SEPARATOR, sub_sources, work_dir, lines, rule_order, depth)


def _emit_terminal_rule(name: str, prefix: str, node: dict, sources: dict, work_dir: str, lines: list,
                        rule_order: list, depth: int) -> None:
    """emits the rule of a terminal node. Mirrors the passing of channels in run._run_terminal_node"""
    node_def = n.get_node_by_hash(node["_hash_of_node_def"])
    if "_image_id" not in node_def:
        details = f"node {name}: bash/nix nodes cannot be exported to snakemake"
        dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)

    inputs, outputs, mounts, envvars, cli_args, output_files, output_dirs, register = [], [], [], [], [], [], [], []
    for node_channel_name, channel in node["input"].items():
        node_channel = node_def["input"][node_channel_name]
        source = sources[channel]
        if source["kind"] in ("file", "directory"):
            inputs.append(source["expr"])
            if "path_in_container" in node_channel:
                mounts.append(f"({source['expr']}, {node_channel['path_in_container']!r})")
            elif "environment_var_in_container" in node_channel:
                envvars.append(f"({node_channel['environment_var_in_container']!r}, {source['expr']})")
            else:
                _invalid_channel(name, node_channel_name)
        elif "environment_var_in_container" in node_channel:
            envvars.append(f"({node_channel['environment_var_in_container']!r}, parma_str({source['expr']}))")
        elif "command_line_parameter" in node_channel:
            cli_args.append(f"{node_channel['command_line_parameter']!r}, parma_str({source['expr']})")
        else:
            _invalid_channel(name, node_channel_name)

    for node_channel_name, channel in node["output"].items():
        node_channel = node_def["output"][node_channel_name]
        source = sources[channel]
        if source["kind"] == "directory":
            if source["storage"] != "extern":  # as in run.py: directories can't be stored in the platform
                details = f"node {name}: directory channel \"{channel}\" must have storage \"extern\""
                dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
            outputs.append(f"directory({source['expr']})")
            output_dirs.append(source["expr"])
        else:
            outputs.append(source["expr"])
            output_files.append(source["expr"])
        if "path_in_container" in node_channel:
            mounts.append(f"({source['expr']}, {node_channel['path_in_container']!r})")
        elif "environment_var_in_container" in node_channel:
            envvars.append(f"({node_channel['environment_var_in_container']!r}, {source['expr']})")
        else:
            _invalid_channel(name, node_channel_name)
        # data name as in run.py: the channel name in the workflow of the node; run channel: prefixed, thus unique
        register.append(f"({source['expr']}, {channel!r}, {source['storage']!r}, {source['kind']!r}, "
                        f"{prefix + channel!r})")

    done_marker = None
    if not outputs:  # Snakemake needs an output to execute a rule
        done_marker = repr(f"{work_dir}/.done/{name}")
        outputs.append(done_marker)
        lines.append(INDENT * depth + f"PARMA_TARGETS.append({done_marker})")

    rule_name = _rule_name(name)
    rule_order.append(rule_name)
    i1, i2, i3 = (INDENT * (depth + k) for k in (1, 2, 3))
    lines.append(INDENT * depth + f"rule {rule_name}:")
    if inputs:
        lines.append(f"{i1}input:")
        lines.extend(f"{i2}{expr}," for expr in inputs)
    lines.append(f"{i1}output:")
    lines.extend(f"{i2}{expr}," for expr in outputs)
    lines.append(f"{i1}run:")
    lines.append(f"{i2}parma_docker_run(")
    lines.append(f"{i3}{rule_name!r}, {name!r}, {node_def['_image_id']!r},")
    lines.append(f"{i3}mounts=[{', '.join(mounts)}],")
    lines.append(f"{i3}envvars=[{', '.join(envvars)}],")
    lines.append(f"{i3}cli_args=[{', '.join(cli_args)}],")
    lines.append(f"{i3}output_files=[{', '.join(output_files)}],")
    lines.append(f"{i3}output_dirs=[{', '.join(output_dirs)}],")
    lines.append(f"{i3}done_marker={done_marker},")
    lines.append(f"{i3}register=[{', '.join(register)}],")
    lines.append(f"{i2})")
    lines.append("")


def _invalid_channel(node_name: str, channel: str) -> None:
    details = f"node {node_name}: channel \"{channel}\" declares neither path, environment var nor command line parameter"
    dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)


def _rule_name(name: str) -> str:
    """a valid python identifier as rule name"""
    rule = re.sub(r"\W", "_", name)
    return rule if rule and not rule[0].isdigit() else "r_" + rule
