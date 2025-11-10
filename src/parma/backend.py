import os
from pathlib import Path
import argparse
import logging
import platform
import sys

import intern.helper as h
import intern.dbc as dbc
import intern.msg as msg
import intern.database as db
import intern.view as v

import component.user as user
import component.node as n
import component.data as d
import component.workflow as wf
import component.run as run

from flask import Flask, request, jsonify


app = Flask(__name__)


@app.errorhandler(Exception)
def handle_exception(e: Exception):
    """
    Flask error handler for all exceptions.

    Args:
        e (Exception): The exception that was raised.

    Returns:
        Response: A Flask JSON response with error details.
    """
    if isinstance(e, dbc.ParmaException):
        return jsonify({"success": False, "parma_exception": e.error_description}), 200
    return jsonify({"success": False, "exception": str(e)}), 200


@app.route("/store", methods=["POST"])
def run_store():
    """
    Endpoint to store all tables to disk.

    Returns:
        Response: A Flask JSON response indicating success.
    """
    db.store_tables()
    return jsonify({"success": True})


@app.route("/get_data", methods=["POST"])
def get_data():
    """
    Endpoint to retrieve data content.

    Returns:
        Response: A Flask JSON response with the data content.
    """
    param = request.json["param"]
    return jsonify(v.get_data(param))


@app.route("/export", methods=["POST"])
def export():
    """
    Endpoint to export a file.

    Returns:
        Response: A Flask JSON response indicating success.
    """
    param = request.json["param"]
    v.export(param)
    return jsonify({"success": True})


@app.route("/login", methods=["POST"])
def run_login():
    """
    Endpoint to log in a user.

    Returns:
        Response: A Flask JSON response with the user hash.
    """
    login_name = request.json["param"]["name"]
    hash = user.login(login_name)
    return jsonify({"success": True, "hash": hash})


@app.route("/user", methods=["POST"])
def add_user():
    """
    Endpoint to add a new user.

    Returns:
        Response: A Flask JSON response with the result.
    """
    return _process_request(request, user.add_user)


@app.route("/data", methods=["POST"])
def add_data():
    """
    Endpoint to add a new data entry.

    Returns:
        Response: A Flask JSON response with the result.
    """
    return _process_request(request, d.add_data)


@app.route("/node", methods=["POST"])
def add_node():
    """
    Endpoint to add a new node.

    Returns:
        Response: A Flask JSON response with the result.
    """
    return _process_request(request, n.add_node)


@app.route("/workflow", methods=["POST"])
def add_workflow():
    """
    Endpoint to add a new workflow.

    Returns:
        Response: A Flask JSON response with the result.
    """
    return _process_request(request, wf.add_workflow)


@app.route("/refine", methods=["POST"])
def add_refine():
    """
    Endpoint to refine a workflow.

    Returns:
        Response: A Flask JSON response with the result.
    """
    return _process_request(request, wf.refine_workflow)


@app.route("/run", methods=["POST"])
def add_run():
    """
    Endpoint to add a new run.

    Returns:
        Response: A Flask JSON response with the result.
    """
    return _process_request(request, lambda param, user: run.run_workflow(param, {}, user))


def _process_request(request, to_be_called):
    """
    Helper function to process API requests for adding users, data, nodes, workflows, runs, etc.

    Args:
        request: The Flask request object.
        to_be_called: The function to call with (param, logged_in_user).

    Returns:
        Response: A Flask JSON response with the result or error.
    """
    try:
        if not request.is_json:
            return jsonify({"success": False, "error": "Request must be JSON"}), 400
        wrapper = request.get_json()
        calling_user = wrapper["authentification_token"]
        db.assert_user_exists(calling_user)
        param = wrapper["param"]
        hash = to_be_called(param, calling_user)
        return jsonify({"success": True, "hash": hash})
    except dbc.ParmaException as p:
        return jsonify({"success": False, "parma_exception": p.error_description})
    except Exception as e:
        return jsonify({"success": False, "exception": f"{e}"})


@app.route("/view/data_of", methods=["POST"])
def view_data_of():
    """
    Endpoint to view data information for a workflow or run.

    Returns:
        Response: A Flask JSON response with data info.
    """
    if not request.is_json:
        dbc.raise_error( {"msg": "SYSTEM_ERROR", "details": "Request must be JSON"}, user_error=False )
    wrapper = request.get_json()
    db.assert_user_exists(wrapper["authentification_token"])
    param = wrapper["param"]
    result, workflow_or_run = v.get_name_version_and_hash_and_entity_of_workflow_or_run_by_referer(param)
    result["table"] = d.get_data_info_from_workflow_or_run(workflow_or_run)
    result["success"] = True
    return jsonify(result)


@app.route("/view/log_of", methods=["POST"])
def view_log_of():
    """
    Endpoint to view the log for a workflow or run.

    Returns:
        Response: A Flask JSON response with the log.
    """
    if not request.is_json:
        dbc.raise_error( {"msg": "SYSTEM_ERROR", "details": "Request must be JSON"}, user_error=False )
    wrapper = request.get_json()
    db.assert_user_exists(wrapper["authentification_token"])
    param = wrapper["param"]
    result, workflow_or_run = v.get_name_version_and_hash_and_entity_of_workflow_or_run_by_referer(param)
    result["log"] = workflow_or_run["_log"]
    result["success"] = True

    return jsonify(result)


@app.route("/view/table", methods=["POST"])
def view_table():
    """
    Endpoint to view a table of users, data, nodes, workflows, or runs.

    Returns:
        Response: A Flask JSON response with the table.
    """
    if not request.is_json:
        dbc.raise_error( {"msg": "SYSTEM_ERROR", "details": "Request must be JSON"}, user_error=False )
    wrapper = request.get_json()
    db.assert_user_exists(wrapper["authentification_token"])
    param = wrapper["param"]
    result = v.view_table(param)
    result["success"] = True
    return jsonify(result)


def main() -> None:
    """
    Main entry point for the parma backend.
    """
    parser = argparse.ArgumentParser(description='Parma Light Backend Server')
    parser.add_argument('-c', '--config', help='toml configuration file path', default='./parma_light.toml')
    parser.add_argument('-d', '--debugpy', help='activate debugpy for remote debugging', default=False, action='store_true')
    args = parser.parse_args()

    # Load toml configuration
    toml_config_file = Path(args.config)
    toml_config = h.load_toml_config(toml_config_file)
    
    # init logging
    logging_level = toml_config.get('logging', {}).get('level', logging.INFO)
    logging_file = '/app/parma_light.log' if h.RUNNING_IN_CONTAINER else toml_config.get('store', {}).get('log_file', './datastore_parma/parma_light.log')
    logging.basicConfig(format='%(asctime)s - %(name)-20s - %(levelname)-8s - %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S',
                        filename=logging_file,
                        encoding='utf-8',
                        level=logging_level)
    logger = logging.getLogger(__name__)

    # Check for remote debugging request
    if args.debugpy:
        if not h.RUNNING_IN_CONTAINER:
            print("Exit 12. Remote debugging can be used only when running in a container")
            sys.exit(12)
        else:
            import debugpy
            debugpy.listen(("0.0.0.0", 5678))
            print("⚡ VS Code debugger can now be attached, press F5 ⚡")
            debugpy.wait_for_client()

    # Get the store configuration
    host_os = os.environ.get("HOST_OPERATING_SYSTEM")
    if h.RUNNING_IN_CONTAINER:
        logger.info("parma light is running in a docker container based on linux")
        entity_store = '/entity_store'
        data_dir = '/data_dir'
        temp_dir = '/temp_dir'
        base_dir = '/base_dir'
        data_dir_for_mount = os.environ.get("PARMA_LIGHT_DATA_DIR_HOST")
        temp_dir_for_mount = os.environ.get("PARMA_LIGHT_TEMP_DIR_HOST")
    else:
        logger.info(f"parma light is running on a local {host_os} machine")
        entity_store = toml_config.get('store', {}).get('entity_store')
        data_dir = toml_config.get('store', {}).get('data_dir')
        temp_dir = toml_config.get('store', {}).get('temp_dir')
        base_dir = toml_config.get('store', {}).get('base_dir')
        data_dir_for_mount = None
        temp_dir_for_mount = None
    db.init(host_os, entity_store, data_dir, temp_dir, base_dir, data_dir_for_mount, temp_dir_for_mount)

    # Get host and port from config or use defaults
    host = toml_config.get('server', {}).get('host', '0.0.0.0')
    port = toml_config.get('server', {}).get('port', 8080)
    kind_of_server = toml_config.get('server', {}).get('server', 'waitress')

    # get tool configuration
    bash_on_linux = toml_config.get('tools', {}).get('bash_on_linux', '/bin/bash')
    bash_on_windows = toml_config.get('tools', {}).get('bash_on_windows', '/bin/bash')
    nix_on_linux = toml_config.get('tools', {}).get('nix_on_linux', '/bin/bash')
    run.init(bash_on_linux, bash_on_windows, nix_on_linux)

    try:
        if kind_of_server == 'development':
            app.run(host=host, port=port)
        elif kind_of_server == 'development_debug':
            app.run(host=host, port=port, debug=True)
        elif kind_of_server == 'waitress':
            from waitress import serve
            msg.log(logger.info, {"msg": "PROD_SERVER", "wsgi": "waitress", "host": host, "port": port})
            serve(app, host=host, port=port)
        else:
            from waitress import serve
            msg.log(logger.error, {"msg": "INVALID_PROPERTY", "property": "server", "replacement": 'waitress'})
            msg.log(logger.info, {"msg": "PROD_SERVER", "wsgi": "waitress", "host": host, "port": port})
            serve(app, host=host, port=port)
    finally:
        db.store_tables()
        db.remove_all_temp_directories()


if __name__ == "__main__":
    main()

