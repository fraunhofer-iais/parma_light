# a helper module for the rest of the code.

import hashlib
import json
import datetime
from pathlib import Path
import re
import secrets
import jsonschema
import yaml
from python_on_whales import docker
from python_on_whales import DockerException
import os
import platform
import stat
import logging
from intern import msg
import intern.dbc as dbc
from werkzeug.security import generate_password_hash, check_password_hash

def _running_in_docker() -> bool:
    """
    Return True if the process likely runs inside a container (Linux).
    Combines several heuristics: /.dockerenv and /proc/1/cgroup.
    """
    import os
    try:
        # quick check: Docker creates this file for many images
        if os.path.exists("/.dockerenv"):
            return True
        # check cgroup info for container runtime indicators
        if os.path.exists("/proc/1/cgroup"):
            with open("/proc/1/cgroup", "rt") as f:
                data = f.read()
            indicators = ("docker", "kubepods", "containerd", "lxc", "podman")
            if any(tok in data for tok in indicators):
                return True
    except Exception:
        pass
    return False


WINDOWS = True if os.name == 'nt' or platform.system() == 'Windows' else False
RUNNING_IN_CONTAINER = _running_in_docker()
logger = logging.getLogger(__name__)


def load_yaml_config(config_file: Path) -> dict:
    """
    Load configuration from YAML file.

    Args:
        config_file (Path): Path to the configuration file

    Returns:
        dict: Configuration dictionary
    """
    try:
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"Exit 12. Error loading yaml-config file: {e}")
        exit(12)


def set_file_readonly(file_path: str) -> None:
    os.chmod(file_path, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def set_file_writable(file_path: str) -> None:
    os.chmod(
        file_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH | stat.S_IWOTH,
    )


def set_file_executable(file_path: str) -> None:
    """
    no effect on windows :-<
    """
    mode = os.stat(file_path).st_mode
    os.chmod(file_path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def get_date() -> str:
    """
    Returns the current date and time as a formatted string.

    Returns:
        str: The current date and time in "%Y-%m-%d %H:%M:%S.%f" format.
    """
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")


def make_git_like_hash_of_bytes(bytes: bytes) -> str:
    """
    Computes a git-like SHA-1 hash for the given bytes.

    Args:
        bytes (bytes): The bytes to hash.

    Returns:
        str: The SHA-1 hash as a hexadecimal string.
    """
    header = f"blob {len(bytes)}\0".encode("utf-8")
    store = header + bytes
    return hashlib.sha1(store).hexdigest()


def make_git_like_hash_of_a_file(filepath: str) -> str:
    """
    Computes a git-like SHA-1 hash for the contents of a file.

    Args:
        filepath (str): The path to the file.

    Returns:
        str: The SHA-1 hash as a hexadecimal string.
    """
    with open(filepath, "rb") as f:
        file_content = f.read()
    return make_git_like_hash_of_bytes(file_content)


def make_git_like_hash_of_json(json_object: dict) -> str:
    """
    Computes a git-like SHA-1 hash for a JSON object.

    Args:
        json_object (dict): The JSON object to hash.

    Returns:
        str: The SHA-1 hash as a hexadecimal string.
    """
    json_string = json.dumps(json_object, indent=4, sort_keys=True)
    return make_git_like_hash_of_bytes(json_string.encode("utf-8"))


PASSWORD_HASH_METHOD = "scrypt"


def make_password_hash(password: str) -> str:
    """
    Computes a salted, deliberately slow hash of a password (scrypt, by werkzeug).

    Args:
        password (str): The plain-text password.

    Returns:
        str: A self-contained string "scrypt:<parameters>$<salt>$<hash>".
    """
    return generate_password_hash(password, method=PASSWORD_HASH_METHOD)


def verify_password_hash(password: str, stored: str) -> bool:
    """
    Verifies a password against a hash made by :func:`make_password_hash`.

    Args:
        password (str): The plain-text password to verify.
        stored (str): The stored hash.

    Returns:
        bool: ``True`` if the password matches, ``False`` otherwise
              (including when *stored* is ``None`` or malformed).
    """
    if not stored:
        return False
    try:
        return check_password_hash(stored, password)
    except Exception:
        return False


def _get_sha256_image_digest(repo_digest: str, image_name: str) -> str:
    """
    Extracts the SHA-256 digest from a Docker image repo digest string.

    Args:
        repo_digest (str): The repository digest string.
        image_name (str): The name of the image.

    Returns:
        str: The SHA-256 digest.
    """
    delimiter = "sha256:"
    index = repo_digest.find(delimiter)
    if index != -1:
        return repo_digest[index + len(delimiter) :]
    else:
        dbc.raise_error({"msg": "IMAGE_PROBLEM", "image_name": image_name}, user_error=False)


def get_docker_image_digest(image: dict) -> str:
    """
    Retrieves the SHA-256 digest of a Docker image, pulling it if necessary.

    Args:
        image (dict): The image dictionary with "name" and "version" or "hash".

    Returns:
        str: The SHA-256 digest of the image.
    """
    counter = 0
    while counter < 3:
        counter += 1
        try:
            if "hash" in image:
                image_name_to_check = image["hash"]
            else:
                image_name_to_check = f'{image["name"]}:{image["version"]}'
            if not docker.image.exists(image_name_to_check):
                docker.image.pull(image_name_to_check)
            if not docker.image.exists(image_name_to_check):
                dbc.raise_error({"msg": "IMAGE_PROBLEM", "image_name": image_name_to_check})
            image_info = docker.image.inspect(image_name_to_check)
            if not image_info.id:
                dbc.raise_error({"msg": "IMAGE_PROBLEM", "image_name": image_name_to_check}, user_error=False)
            if counter > 1:
                msg.log(logger.info, {"msg": "DOCKER_ACCESS_SUCCEEDED"})
            return _get_sha256_image_digest(image_info.id, image_name_to_check)
        except DockerException:
            msg.log(logger.error, {"msg": "DOCKER_ACCESS_RETRY"})
    dbc.raise_error({"msg": "IMAGE_PROBLEM", "image_name": image_name_to_check}, user_error=False)


def check_that_node_channels_are_bound(
    nodes: dict,
    get_node_by_hash: callable,
    get_workflow_by_hash: callable
) -> None:
    """
    Checks whether all input and output channels of nodes and sub-workflows are bound.
    Prints a warning for each unbound channel.

    Args:
        nodes (dict): The nodes to be checked.
        get_node_by_hash (callable): Function to retrieve a node by its hash.
        get_workflow_by_hash (callable): Function to retrieve a workflow by its hash.

    Returns:
        None
    """
    for node in nodes.values():
        if "_hash_of_node_def" in node:
            node_used = get_node_by_hash(node["_hash_of_node_def"])
            for node_channel_name in node_used["input"]:
                if node_channel_name not in node["input"]:
                    node_hash = node["_hash_of_node_def"]
                    msg.log(logger.error, {"msg": "CHANNEL_NOT_BOUND", "name": node_channel_name, "hash": node_hash, "direction": "input", "what": "node"})
            for node_channel_name in node_used["output"]:
                if node_channel_name not in node["output"]:
                    node_hash = node["_hash_of_node_def"]
                    msg.log(logger.error, {"msg": "CHANNEL_NOT_BOUND", "name": node_channel_name, "hash": node_hash, "direction": "output", "what": "node"})
        elif "_hash_of_workflow_def" in node:
            node_used = get_workflow_by_hash(node["_hash_of_workflow_def"])
            node_hash = node["_hash_of_workflow_def"]
            for node_channel_name in node_used["input"]:
                if node_channel_name not in node["input"]:
                    msg.log(logger.error, {"msg": "CHANNEL_NOT_BOUND", "name": node_channel_name, "hash": node_hash, "direction": "input", "what": "sub workflow"})
            for node_channel_name in node_used["output"]:
                if node_channel_name not in node["output"]:
                    msg.log(logger.error, {"msg": "CHANNEL_NOT_BOUND", "name": node_channel_name, "hash": node_hash, "direction": "output", "what": "sub workflow"})


def opt_hash_by_key_value_and_version(dict: dict, key_value: str, version: str) -> str:
    """
    Retrieves the hash of a data entry by the value of key "name" and version.

    Args:
        dict (dict): The dictionary containing the data entries.
        key_value (str): The value of the key "name" to search for.
        version (str): The integer number of the version to retrieve or "latest".

    Returns:
        str: The hash of the data entry matching version, or None if not found.
    """
    if version == "latest":
        version = 0
    else:
        version = int(version)
    current_version = 0
    current_hash = None
    for hash in dict.keys():
        data = dict[hash]
        if data["name"] == key_value:
            if data["_version"] == version:
                return hash
            if data["_version"] > current_version:
                current_version = data["_version"]
                current_hash = hash
    return current_hash


def opt_hash_by_shrinked_hash(dict: dict, shrinked_hash: str) -> str:
    """
    Retrieves the hash of a data entry by its shrinked hash.

    Args:
        dict (dict): The dictionary containing the data entries.
        shrinked_hash (str): The shrinked hash.

    Returns:
        str: The hash of the data entry matching version, or None if not found.
    """
    for hash in dict.keys():
        if hash.startswith(shrinked_hash):
            return hash
    return None


def get_next_free_version(dict: dict, key_value: str) -> int:
    """
    Returns the next free (not taken) version for the key "name".

    Args:
        dict (dict): The dictionary containing the data entries.
        key_value (str): The value of the key "name" whose version is looked up.

    Returns:
        int: The next free (not taken) version.
    """
    current_version = 0
    for data in dict.values():
        if data["name"] == key_value:
            if data["_version"] > current_version:
                current_version = data["_version"]
    return current_version + 1


def validate_user_input(instance: dict, definition_key: str) -> None:
    """
    Validate a JSON object entered by the user against the schema.

    Args:
        instance (dict): The JSON object to validate.
        definition_key (str): The key in the schema to validate against.

    Raises:
        Raises an error if validation fails.
    """
    dbc.assert_true(instance, {"msg": "INVALID_COMMAND"})
    try:
        jsonschema.validate(instance=instance, schema=_schema["$defs"][definition_key], resolver=_resolver)
    except jsonschema.exceptions.ValidationError as e:
        dbc.raise_error( { "msg": "VALIDATION_ERROR", "definition_of": definition_key, "error": e.message } )


# Precompiled regular expressions
pattern_split_on_first_whitespace = re.compile("^([^ ]*)[ ]*(.*)$")


def split_on_first_whitespace(input_string: str) -> tuple[str, str]:
    """
    Splits the input string on the first whitespace.

    Args:
        input_string (str): The string to split.

    Returns:
        tuple: A tuple (first_word, rest_of_string).
    """
    match = pattern_split_on_first_whitespace.match(input_string)
    if match:
        return (match.group(1), match.group(2))
    else:
        dbc.raise_error({"msg": "INVALID_COMMAND"})


def parse_upload_content(content: str, keywords) -> list:
    """
    Parses the text of an uploaded file into a list of definitions. Accepted are
    - plain JSON: an object or a list of objects. They get the first keyword, or
    - the command file format: one or more blocks "<keyword> { ... }", each optionally terminated by ";".
      Every block may use any of the keywords (e.g. "workflow" and "refine" in one file).

    Args:
        content (str): The uploaded text.
        keywords (str or list[str]): The accepted keyword(s), e.g. "node" or ["workflow", "refine"].

    Returns:
        list[tuple[str, object]]: (keyword, definition) for every definition, in the order of the text.

    Raises:
        Raises an error if the text is neither valid JSON nor in the command file format.
    """
    if isinstance(keywords, str):
        keywords = [keywords]
    decoder = json.JSONDecoder()
    text = (content or "").strip()
    try:
        if not text or text[0] in "{[":
            parsed = json.loads(text)
            items = parsed if isinstance(parsed, list) else [parsed]
            return [(keywords[0], item) for item in items]
        definitions = []
        pos = 0
        while pos < len(text):
            keyword = _keyword_at(text, pos, keywords)
            if keyword is None:
                expected = " or ".join(f"\"{k}\"" for k in keywords)
                dbc.raise_error({"msg": "INVALID_JSON_SYNTAX", "json_msg": f"{expected} expected",
                                 "pos": pos, "context": text[max(0, pos - 20):pos + 20]})
            pos = _skip_whitespace(text, pos + len(keyword))
            obj, pos = decoder.raw_decode(text, pos)
            definitions.append((keyword, obj))
            pos = _skip_whitespace(text, pos)
            if pos < len(text) and text[pos] == ";":
                pos = _skip_whitespace(text, pos + 1)
        return definitions
    except json.JSONDecodeError as e:
        dbc.raise_error({"msg": "INVALID_JSON_SYNTAX", "json_msg": e.msg,
                         "pos": e.pos, "context": e.doc[max(0, e.pos - 20):e.pos + 20]})


def _keyword_at(text: str, pos: int, keywords: list):
    """returns the keyword starting at pos (followed by whitespace or "{"), or None"""
    for keyword in sorted(keywords, key=len, reverse=True):
        end = pos + len(keyword)
        if text.startswith(keyword, pos) and end < len(text) and (text[end].isspace() or text[end] == "{"):
            return keyword
    return None


def _skip_whitespace(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def strip_internal_fields(obj):
    """
    Returns a copy of a stored entry without the fields created by the backend (keys starting with "_"),
    on all levels. User defined keys (names of channels, nodes, ...) never start with "_".
    """
    if isinstance(obj, dict):
        return {key: strip_internal_fields(value) for key, value in obj.items() if not str(key).startswith("_")}
    if isinstance(obj, list):
        return [strip_internal_fields(value) for value in obj]
    return obj


def export_definition(keyword: str, entry: dict) -> str:
    """
    Converts a stored entry (node, workflow, ...) into the text format of uploads ('<keyword> { ... };'),
    without internal fields. Uploading this text creates the entry again (as a new version).
    """
    return f"{keyword} {json.dumps(strip_internal_fields(entry), indent=4)};\n"


def value_matches_type(value, channel_type: str) -> bool:
    """
    Checks whether a JSON value matches a constant channel type (str, int, float, bool, json).
    json accepts every JSON value. bool is not accepted as int or float.
    """
    if channel_type == "str":
        return isinstance(value, str)
    if channel_type == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if channel_type == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if channel_type == "bool":
        return isinstance(value, bool)
    return channel_type == "json"


def value_to_str(value, channel_type: str) -> str:
    """
    Converts a constant to the string passed to a node (as environment variable or command line parameter).
    bool becomes "true"/"false", json is serialized (a string is passed unchanged), everything else uses str().
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if channel_type == "json" or isinstance(value, (dict, list)) or value is None:
        return json.dumps(value)
    return str(value)


def all_keys_different(list_array: list[list]) -> None:
    """
    Checks that all items in a list of lists (array of arrays) are disjoint (no element appears in more than one sublist).
    Throws an exception if the sublists are not disjoint.

    Args:
        list_array (list): List of lists to check.

    Raises:
        Raises an error if duplicate items are found.
    """
    seen = set()
    for sublist in list_array:
        for item in sublist:
            if item in seen:
                dbc.raise_error({"msg":"DUPLICATE_CHANNEL", "name": item})
            seen.add(item)
    return


# Construct an absolute path to the schema for user input, load it including the resolver
def _load_schema(file_path):
    with open(file_path, 'r') as schema_file:
        return json.load(schema_file)


_schema_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema-def-for-user-commands.json")
_schema = _load_schema(_schema_file_path)
_resolver = jsonschema.RefResolver(base_uri=f"file://{_schema_file_path}", referrer=_schema)
