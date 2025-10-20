import os
import copy
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


def get_run_hash_by_referer(referer: dict) -> str:
    """
    Retrieves the hash of a run entry by using a referer.

    Args:
        referer (dict): Must have 'name' and 'version' properties, or a 'hash' property, but NOT both.

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
    _add_to_log(run, f"*** workflow {run['name']} started ***", log_message=True)
    h.check_that_node_channels_are_bound(run["nodes"], n.get_node_by_hash, wf.get_workflow_by_hash)
    
    result = True
    for node_name in run["_topological_order"]:
        _add_to_log(run, f"node: {node_name}", log_message=True)
        node = run["nodes"][node_name]
        if "node" in node:  # a terminal node, a docker image
            result = _run_terminal_node(node, run, channel_bindings, logged_in_user)
        elif "workflow" in node:  # a workflow embedded in another workflow
            result = _run_workflow_node(node_name, node, run, channel_bindings, logged_in_user)
        if not result:
            break
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
    return db.enrich_and_store_in_table(db._run, run, logged_in_user)

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
                    path_outside = d.get_path_by_hash(dynamic_binding["hash_of_data"])
                    path_inside = node_channel["path_in_container"]
                    mounts.append((path_outside, path_inside))
                elif dynamic_binding["type"] == "environment_var":
                    envvar_name = node_channel["environment_var_in_container"]
                    envvar_value = dynamic_binding["value"]
                    envvars.append((envvar_name, envvar_value))
                else:
                    details = f"invalid input binding \"{str(dynamic_binding)}\""
                    dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
        elif channel_rename in run["bind"]:
            dynamic_binding = run["bind"][channel_rename]
            if dynamic_binding["type"] == "file" or dynamic_binding["type"] == "directory":
                hash_of_data = d.get_data_hash_by_referer(dynamic_binding["data"])
                path_outside = d.get_path_by_hash(hash_of_data)
                path_inside = node_channel["path_in_container"]
                mounts.append((path_outside, path_inside))
            elif dynamic_binding["type"] == "environment_var":
                envvar_name = node_channel["environment_var_in_container"]
                envvar_value = dynamic_binding["environment_var_value"]
                envvars.append((envvar_name, envvar_value))
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
        path_inside = node_channel["path_in_container"]

        platform_storage = not "storage" in binding_defined_in_run or binding_defined_in_run["storage"] == "platform"
        if platform_storage and binding_defined_in_run["type"] == "file":
            temp_dir = db.create_a_temp_directory()
            temp_dirs.add(temp_dir)
            path_outside = os.path.join(temp_dir, channel_rename)
            _prepare_output_file(path_outside)
        elif not platform_storage and binding_defined_in_run["type"] == "file":
            path_outside = binding_defined_in_run["user_path"]
            path_outside = os.path.abspath(path_outside)
            _prepare_output_file(path_outside)
        elif not platform_storage and binding_defined_in_run["type"] == "directory":
            path_outside = binding_defined_in_run["user_path"]
            path_outside = os.path.abspath(path_outside)
            _prepare_output_directory(path_outside)
        else:
            details = f"invalid combination of \"storage\" and \"path\" for channel \"{str(channel_rename)}\" (pre docker)"
            dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
        mounts.append((path_outside, path_inside))
        output_channel_to_path[channel_rename] = {"path_outside": path_outside, "binding_defined_in_run": binding_defined_in_run, "node_channel": node_channel}

    image_id = node_def["_image_id"]
    result = _run_docker_as_subprocess(run, image_id, mounts, envvars)

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
    _add_to_log(run, f"docker run finished. Success: {result}")
    return result

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
    _add_to_log(run, f"sub workflow \"{workflow_name}\" finished. Result: {result}, Hash: {shrinked_hash}")
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

def _run_docker_as_subprocess(run: dict, image_name: str, mounts: list, envvars: list) -> bool:
    """
    Runs a Docker image as subprocess.

    Args:
        run (dict): The run entry.
        image_name (str): The name of the Docker image to run.
        mounts (list of tuples): A list of mounts, where each tuple contains (host_path, container_path).
        envvars (list of tuples): A list of bindings of environment var values to environment vars

    Returns:
        bool: True if the command was successful, False otherwise.
    """
    command = ["docker", "run", "--rm"]
    for host_path, container_path in mounts:
        if not os.path.isfile(host_path) and not os.path.isdir(host_path):
            details = f"Mount error: {host_path} is not a file (only file and directory mounts are allowed)"
            _add_to_log(run, details)
            dbc.raise_error({"msg": "SYSTEM_ERROR", "details": details}, user_error=False)
        command.extend(["-v", f"{host_path}:{container_path}"])
    for env_name, env_val in envvars:
        command.extend(["-e", f"{env_name}={env_val}"])
    command.append(image_name)

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
        details = f"Error: Docker run failed with return code {e.returncode}"
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
        subprocess.run(["chmod", "ugo+w", file_path], check=True)
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
