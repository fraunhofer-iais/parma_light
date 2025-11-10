import argparse
import json
from pathlib import Path
import requests

import intern.helper as h
import intern.dbc as dbc
import intern.msg as msg
import intern.read_user_cmd as ruc


BASE_URL: str = "http://localhost:8080"
_authentification_token: str = None  # set by login and reset by logout, used in many requests to the backend
_pattern: str = None  # filter for table data
_limit: str = None  # filter for table data
_errors: int = 0


def run_a_command(input: str, log: bool) -> bool:
    """
    Parses and executes a single user command.

    Args:
        input (str): The command string entered by the user.
        log (bool): If True, prints the command before execution.

    Returns:
        bool: False if the command is 'exit' or 'quit', True otherwise.
    """
    global _authentification_token, _errors
    if log:
        msg.print({"msg": "INPUT_COMMAND", "command": input})
    try:
        cmd, raw_param = h.split_on_first_whitespace(input)
        if cmd == "exit" or cmd == 'quit':
            return False
        elif cmd == "store":
            _post_and_check
            param = {"authentification_token": _authentification_token, "param": {}}
            result = _post_and_check("store", param)
            if result:
                msg.print({"msg": "SUCCESS"})
        elif cmd == "//":
            pass
        elif cmd == "redirect":
            try:
                with open(raw_param, 'r') as f:
                    cmd = ''
                    for line in f:
                        if line.startswith("//"):
                            continue
                        line = line.strip()
                        if line.endswith(';'):
                            cmd += line[:-1]
                            if not run_a_command(cmd, True):
                                break
                            cmd = ''
                        else:
                            cmd += line
            except FileNotFoundError:
                dbc.raise_error({"msg": "NOT_FOUND", "kind": "file", "name": raw_param})
        elif cmd == "login":
            param = {"authentification_token": "", "param": {"name": raw_param}}
            result = _post_and_check("login", param)
            if result:
                _authentification_token = result["hash"]
                msg.print({"msg": "SUCCESS"})
        elif cmd == "logout":
            _authentification_token = None
            msg.print({"msg": "SUCCESS"})
        elif cmd == "locale":
            msg.set_locale(raw_param)
            msg.print({"msg": "SUCCESS"})
        # the following commands are used for debugging
        elif cmd == "test_data":
            if raw_param == "" or raw_param == "sklearn":
                _load_test_data("sklearn")
            elif raw_param == "directory":
                _load_test_data("directory")
            elif raw_param == "array":
                _load_test_data("array")
            elif raw_param == "example:sklearn":
                _load_test_data("example:sklearn")
            elif raw_param == "all":
                _load_test_data("sklearn")
                _load_test_data("directory")
                _load_test_data("array")
                _load_test_data("example:sklearn")
            else:
                dbc.raise_error({"msg": "INVALID_COMMAND"})
            run_a_command("errors", True)
            run_a_command("store", True)
        elif cmd == "errors":
            msg.print({"msg": "ERROR_COUNT", "number": _errors})
            _errors = 0
        elif cmd == "expand":
            pass # print(f"{raw_param} -> {db.get_hash_from_prefix(raw_param)}")
        elif cmd == "dbc":
            if raw_param == "user":
                dbc.raise_error({"msg": "INVALID_COMMAND"})
            elif raw_param == "system":
                dbc.raise_error({"msg": "INVALID_COMMAND"}, user_error=False)
            elif raw_param == "invalid-msg":
                dbc.raise_error({"msg": "INVALID_MESSAGE", "cmd": cmd}, user_error=False)
            elif raw_param == "invalid-key":
                dbc.raise_error(
                    {"msg": "INVALID_LOCALE", "invalid": cmd}, user_error=False)
            else:
                dbc.raise_error({"msg": "NO_USER_LOGGED_IN", "cmd": cmd})
        # end of debugging commands

        # all subsequent calls to endpoints need a wrapper with the authentification_token
        else:
            param = {"authentification_token": _authentification_token}
            global _pattern, _limit
            if cmd == "view" or cmd == "show":
                sub_cmd, view_param = h.split_on_first_whitespace(raw_param)
                if sub_cmd == "pattern":
                    _pattern = view_param
                elif sub_cmd == "limit":
                    _limit = view_param
                elif sub_cmd == "reset":
                    _pattern = None
                    _limit = None
                elif sub_cmd in ["data_of", "do"]:
                    param["param"] =  _user_input2json(view_param)
                    result = _post_and_check("view/data_of", param)
                    if result:
                        msg.print({"msg":"NAME_VERSION_HASH", "name": result["name"], "version": result["_version"], "hash": result["hash"]})
                        _print_table(result["table"])
                elif sub_cmd in ["log_of", "lo"]:
                    param["param"] =  _user_input2json(view_param)
                    result = _post_and_check("view/log_of", param)
                    if result:
                        msg.print({"msg":"NAME_VERSION_HASH", "name": result["name"], "version": result["_version"], "hash": result["hash"]})
                        print("----------------------------------------")
                        for line in result["log"]:
                            print(line)
                        print("----------------------------------------")
                elif sub_cmd in ["user","data","node","workflow","run"]:
                    param["param"] = {"name": sub_cmd, "pattern": _pattern, "limit": _limit}
                    result = _post_and_check("view/table", param)
                    if result:
                        _print_table(result["table"])
            elif cmd == "cat":
                param["param"] = _user_input2json(raw_param)
                result = _post_and_check("get_data", param)
                if result:
                    print(f"name: {result['name']} version: {result['version']} hash: {result['hash']}")
                    print(result["content"])
            elif cmd == "export":
                param["param"] = _user_input2json(raw_param)
                result = _post_and_check("export", param)
                if result:
                    msg.print({"msg": "SUCCESS"})
            elif cmd in ["user","data","node","workflow","refine"]:
                param["param"] = json.loads(raw_param)
                result = _post_and_check(f"{cmd}", param)
                if result:
                    msg.print({"msg": "SUCCESS"})
            elif cmd == "run":
                param["param"] = json.loads(raw_param)
                result = _post_and_check("run", param)
                if result:
                    msg.print({"msg": "SUCCESS"})
                    run_a_command(f"view data_of {result['hash']}", False)
            else:
                dbc.raise_error({"msg": "INVALID_COMMAND"})
    except Exception as e:
        message_text = msg.get_message_text_for_exception(e)
        msg.print({"msg": "COMMAND_IGNORED", "message_text": message_text}, prefix_with_error=True)
        _errors += 1
    return True


def _user_input2json(user_input: str) -> dict:
    """
    Converts user input into a JSON-compatible dictionary for backend requests.

    Args:
        user_input (str): The user input string.

    Returns:
        dict: The parsed input as a dictionary.
    """
    user_input = user_input.strip()
    try:
        if user_input.startswith("{"):
            return json.loads(user_input)
    except Exception:
        pass
    if " " in user_input:
        # its "name" and "version"
        name, version = user_input.split(" ", 1)
        return {"name": name, "version": version}
    # its hash
    return {"hash": user_input}


def _print_table(table: list[list]) -> None:
    """
    Prints a 2D array (list of lists) in a tabular format with aligned columns.

    Args:
        table (list[list]): A 2D array where each inner list represents a row of the table.

    Example:
        table = [
            ["Name", "Age", "City"],
            ["Reinhard", 74, "Köln"],
            ["Inte", 60, "Köln"],
            ["Laura", 27, "Witzenhausen"],
            ["Felix", 26, "Sonthofen"],
        ]
        print_table(table)

    Output:
        Name      | Age | City          
        Reinhard  | 74  | Köln      
        Inte      | 60  | Köln 
        Laura     | 27  | Witzenhausen
        Felix     | 25  | Sonthofen   
    """
    col_widths = [max(len(str(item)) for item in col) for col in zip(*table)]
    for row in table:
        print(" | ".join(f"{item:<{col_widths[i]}}" for i, item in enumerate(row)))


def _post_and_check(endpoint: str, param: dict) -> dict:
    """
    Sends a POST request to the backend and checks the result.

    Args:
        endpoint (str): The backend endpoint to call.
        param (dict): The parameters to send in the request.

    Returns:
        dict: The backend response if successful, None otherwise.
    """
    try:
        result = requests.post(f"{BASE_URL}/{endpoint}", json=param).json()
        return _show_error(result)
    except Exception as e:
        print(f"FRONTEND ERROR: {e}")
    return None


def _show_error(result: dict) -> dict:
    """
    Handles and prints errors from backend responses.

    Args:
        result (dict): The backend response.

    Returns:
        dict: The result if successful, None otherwise.
    """
    global _errors
    if result.get("success") == True:
        return result
    else:
        _errors += 1
        if "parma_exception" in result:
            msg.print(result['parma_exception'], prefix_with_error=True)
        elif "exception" in result:
            msg.print({"msg": "BACKEND_EXCEPTION", "exception": result['exception']}, prefix_with_error=True)
        else:
            msg.print({"msg": "BACKEND_ERROR"}, prefix_with_error=True)
    return None


def _load_test_data(domain: str) -> None:
    """
    Loads a set of test data into the database by executing a series of commands.

    Args:
        domain (str): The test data domain to load (e.g., "sklearn", "array", "directory", "example:sklearn").

    Returns:
        None
    """
    run_a_command("login root", True)
    if domain == "sklearn":
        run_a_command("redirect test/test_cmds/sklearn/user.txt", True)
        run_a_command("redirect test/test_cmds/sklearn/data.txt", True)
        run_a_command("redirect test/test_cmds/sklearn/node.txt", True)
        run_a_command("redirect test/test_cmds/sklearn/node.txt", True)
        run_a_command("redirect test/test_cmds/sklearn/workflow.txt", True)
        run_a_command("redirect test/test_cmds/sklearn/run.txt", True)
        run_a_command("redirect test/test_cmds/sklearn/workflowsub_and_run.txt", True)
    elif domain == "array":
        run_a_command("redirect test/test_cmds/array/process_array.txt", True)
        run_a_command("redirect test/test_cmds/array/process_array_with_subworkflow.txt", True)
    elif domain == "directory":
        run_a_command("redirect test/test_cmds/directory/demo.txt", True)
    elif domain == "example:sklearn":
        run_a_command("redirect example/sklearn/demo.txt", True)


def main() -> None:
    """
    Main entry point for the parma CLI application.
    Runs commands in an endless loop.

    Returns:
        None
    """
    parser = argparse.ArgumentParser(description='Parma Light Frontend CLI')
    parser.add_argument('-c', '--config', help='Toml configuration file path', default='./parma_light.toml')
    args = parser.parse_args()

    # Load toml configuration
    toml_config_file = Path(args.config)
    toml_config = h.load_toml_config(toml_config_file)

    # Get frontend properties
    history_file = toml_config.get('history', {}).get('file', 'parma_light_cli_history')
    ruc.init(history_file)
    
    last_command = "view run"
    while True:
        user_input = ruc.read_user_command()
        if user_input == "!!":
            user_input = last_command
        if not run_a_command(user_input, False):
            break
        last_command = user_input
    ruc.write_history_file()


if __name__ == "__main__":
    main()
