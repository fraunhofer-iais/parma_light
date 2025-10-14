import builtins
import traceback
from typing import Dict, Any

from json import JSONDecodeError
from jsonschema import SchemaError
from python_on_whales import DockerException
import intern.dbc as dbc


print_exception: bool = True
"""Flag to control whether to print exceptions."""

current_locale: str = "en"
"""The current locale for error messages. Default is 'en'."""

messages_en: Dict[str, str] = {
    "ACCESS_DENIED": "access denied. Please check your permissions.",
    "DIRECTORY_RESTRICTION": "currently directory \"{path}\" can neither be copied to the platform nor hashed",
    "DOCKER_ERROR": "there was a problem with Docker. Is the Docker daemon running?",
    "DUPLICATE_CHANNEL": "channel \"{name}\" used twice.",
    "ERROR_COUNT": "accumulated number of errors is \"{number}\". Counter is reset",
    "BACKEND_EXCEPTION": "exception occured in backend: \"{exception}\"",
    "BACKEND_ERROR": "programming error detected in backend",
    "HASH_MISMATCH": "file \"{path}\" was modified after it has been added to the platform",
    "IMAGE_PROBLEM": "the specified image \"{image_name}\" was not found or erroneous. Please check it and try again.",
    "INVALID_CHANNEL": "the workflow is invalid. Please check the channel \"{name}\".",
    "INVALID_COMMAND": "the command you entered is invalid. Please refer to 'resources/APIDOC.md'.",
    "INVALID_CHANNEL_DEF": "\"storage\", \"hash\" and \"user_path\" required for \"type\":\"directory\", but forbidden for files",
    "INVALID_HASH": "you entered an hash \"{prefix}\" that does not exist.",
    "INVALID_JSON_SYNTAX": "invalid JSON syntax. \"{json_msg}\". Error at char {pos}, char sourronding are >>>{context}<<<.",
    "INVALID_LOCALE": "the locale \"{locale}\" is not supported. E.g. use 'en' for English.",
    "INVALID_MESSAGE": "invalid error processing for error \"{exception}\".",
    "INVALID_SCHEMA": "invalid JSON, Jsonschema error. \"{schema_error}\".",
    "INVALID_WORKFLOW": "the workflow is invalid. Reason: \"{reason}\". Please check the workflow definition.",
    "MUST_BE_SUPERUSER": "you must be a superuser to perform this action.",
    "NODE_CHANNEL_MISSING_IN_WF_CHANNELS": "channel \"{channel_name}\" of {node_type} \"{referer_name}\" not in the workflow's channel declaration.",
    "NODE_DEF_AND_USE_MISMATCH": "channels of {node_type} \"{referer_name}\" don't match the channels usage in the workflow",
    "NO_FILE_OR_NOT_FOUND": "\"{name}\" not found or is no file",
    "NO_MESSAGE_KEY": "no message key provided.",
    "NO_USER_LOGGED_IN": "no user logged in. Please log in to continue.",
    "NOT_FOUND": "the {kind} was not found. Please check \"{name}\" and try again.",
    "NYI": "sorry, but this feature is not yet implemented.",
    "REFINE_MISMATCH": "channels or binds of a replacement in a refine declaration don't match with the original workflow",
    "SYSTEM_ERROR": "internal error. Details: \"{details}\".",
    "UNPROCESSED_EXCEPTION": "an unprocessed exception of type \"{exception_type}\" occurred.",
    "USER_ALREADY_EXISTS": "the user \"{name}\" already exists. Please choose a different name.",
    "VALIDATION_ERROR": "error when validating \"{definition_of}\": \"{error}\".",
    "WORKFLOW_CHANNEL_UNUSED": "the workflow channel \"{channel_name}\" is not used in a node.",
    
    "CHANNEL_NOT_BOUND": "WARNING: {direction} channel {name} of {what} {hash} not bound",
    "COMMAND_IGNORED": "command ignored. Error message is: \"{message_text}\"",
    "DOCKER_ACCESS_RETRY": "retrying access to docker (internal problem of python_on_whales)",
    "DOCKER_ACCESS_SUCCEEDED": "eventually access to docker succeeded",
    "HISTORY_WRITTEN": "history file written to \"{file}\"",
    "INPUT_COMMAND": "exec: {command}",
    "NAME_VERSION_HASH": "name: {name}, version: {version}, hash: {hash}",
    "NO_LOG_DATA": "no logging data found",
    "NUMBER_DATA_CREATED": "the run created {number} new data entity/ies",
    "NUMBER_HEX_DIGITS": "the number of hex digits to uniquely identify a hash is {number} now",
    "PROD_SERVER": "Starting production server on {host}:{port}",
    "RM_TMPDIR": "all temporary directories removed",
    "STORED_TABLE": "table {name} is stored",
    "STORE": "entities: {entity_store}\ndata: {data_dir}\ntemp: {temp_dir}",
    "SUCCESS": "command was successful"
}

messages_de: Dict[str, str] = {}


def set_locale(locale: str) -> None:
    """
    Set the locale for error messages.

    Args:
        locale (str): The locale to set (e.g., "de" for German, "en" for English).

    Raises:
        ParmaException: If the provided locale is not supported.
    """
    global current_locale
    if locale not in ["en"]:
        dbc.raise_error({"msg": "INVALID_LOCALE", "locale": locale})
    current_locale = locale


def print(msgkey_and_params: Dict[str, Any], prefix_with_error: bool = False) -> None:
    """
    Print a message text as defined by a message key. The message dictionary contains the message key and its parameters.
    The message is localized based on the current locale.

    Args:
        msgkey_and_params (dict): Message key and its parameters.
        prefix_with_error (bool, optional): If True, prefix the message with "*** ERROR ***". Default is False.
    """
    msgkey_and_params["category"] = "USER_ERROR"
    if prefix_with_error:
        builtins.print(f"*** ERROR *** {get_message_text(msgkey_and_params)}")
    else:
        builtins.print(get_message_text(msgkey_and_params))


def get_message_text(msgkey_and_params: Dict[str, Any]) -> str:
    """
    Create a message text from a dictionary. The dictionary contains the message key and its parameters.
    The message is localized based on the current locale.

    Args:
        msgkey_and_params (dict): Message key and its parameters.

    Returns:
        str: The formatted error message.
    """
    if not isinstance(msgkey_and_params, dict):
        return error_in_message_handling("message is no dict")
    if msgkey_and_params.get("category", "SYSTEM_ERROR") == "USER_ERROR":
        msg_context = ""
    else:
        msg_context = (
            " !!! This is a system error. Please contact the developer team !!!"
        )
    message_key = msgkey_and_params.get("msg", "--NO_MESSAGE_KEY--")
    messages = messages_de if current_locale == "de" else messages_en
    message = messages.get(message_key, "--NO_MESSAGE--")
    if message == "--NO_MESSAGE--":
        return get_message_text({"msg": "SYSTEM_ERROR", "details": "message key not found"})
    return message.format(**msgkey_and_params) + msg_context


def get_message_text_for_exception(exception: Exception) -> str:
    """
    Retrieve the localized error message for a given exception.
    Prints stack trace if print_exception is True.

    Args:
        exception (Exception): The exception object.

    Returns:
        str: The formatted error message.
    """
    if isinstance(exception, dbc.ParmaException):
        try:
            return get_message_text(exception.args[0])
        except Exception as e:
            return error_in_message_handling("message is no dict")
    if isinstance(exception, DockerException):
        return get_message_text({"msg": "DOCKER_ERROR", "category": "SYSTEM_ERROR"})
    if isinstance(exception, FileNotFoundError):
        return get_message_text( { "msg": "NOT_FOUND", "kind": "file", "name": exception.filename, "category": "USER_ERROR"} )
    if isinstance(exception, JSONDecodeError):
        pm = 40
        pos = exception.pos
        from_pos = pos - pm if pos - pm >= 0 else 0
        to_pos = pos + pm if len(exception.doc) >= pos + pm else len(exception.doc) - 1
        doc_context = exception.doc[from_pos:to_pos]
        return get_message_text({
            "msg": "INVALID_JSON_SYNTAX",
            "json_msg": exception.msg,
            "context": doc_context,
            "pos": pos,
            "category": "USER_ERROR"})
    if isinstance(exception, KeyError):
        details = f"key \"{exception.args[0]}\" not found"
        return get_message_text({"msg": "SYSTEM_ERROR", "details": details, "category": "SYSTEM_ERROR"})
    if isinstance(exception, TypeError):
        details = f"type error: \"{exception.args[0]}\""
        return get_message_text({"msg": "SYSTEM_ERROR", "details": details, "category": "SYSTEM_ERROR"})
    if isinstance(exception, SchemaError):
        return get_message_text({"msg": "INVALID_SCHEMA", "schema_error": exception.message, "category": "SYSTEM_ERROR"})
    # add more lines before to process more special exceptions
    return error_in_message_handling("unexpected exception \"{}\"in get_message_text_for_exception")


def error_in_message_handling(details: str) -> str:
    """
    Handle errors that occur during message processing. Be careful, when changing this: it is used for error processing,
    thus there is a potential for an endless loop :-)

    Args:
        details (str): Indication of the internal error.

    Returns:
        str: A message indicating an unprocessed exception.
    """
    traceback.print_exc()
    return get_message_text({"msg": "SYSTEM_ERROR", "details": details})


def referer2str(referer: Dict[str, Any]) -> str:
    """
    Converts a referer dictionary to a human-readable string representation.

    Args:
        referer (dict): The referer object, which may contain "name", "version", or "hash" keys.

    Returns:
        str: A string describing the referer, including name and version or hash if present.
    """
    if "name" in referer or "version" in referer:
        return f'name: {referer.get("name","---")}, version: {referer.get("version","---")}'
    elif "hash" in referer:
        return f'hash: {referer.get("hash","---")}'
    else:
        return "---"