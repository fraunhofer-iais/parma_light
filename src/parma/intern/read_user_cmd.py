import os
import platform
from typing import Optional

from intern import msg

history_file: Optional[str] = None
WINDOWS = True if os.name == 'nt' or platform.system() == 'Windows' else False

def init(history_file_from_properties):
    if not WINDOWS:
        # Configure readline for history and editing
        import readline
        history_file = history_file_from_properties
        try:
            readline.read_history_file(history_file)  # type: ignore
        except FileNotFoundError:
            pass
        readline.set_history_length(1000)  # type: ignore


def write_history_file() -> None:
    """
    Writes the command history to the history file if the system is not Windows.
    This function uses the `readline` module to save the command history to a file.

    Returns:
        None
    """
    if not WINDOWS:
        readline.write_history_file(history_file)  # type: ignore
        msg.print({"msg": "HISTORY_WRITTEN", "file": history_file})


def read_user_command() -> str:
    """
    Reads a user command from the terminal. A command is terminated by a ";" and may be multiline.

    On non-Windows systems, it uses the `readline` module to provide
    command-line editing and history support. On Windows systems, it
    falls back to basic input handling and a limited "!!" facility.

    Returns:
        str: The user input command as a string.
    """
    lines: list[str] = []
    command_complete: bool = False
    while not command_complete:
        line: str = input("parma cmd: " if not lines else "... ")
        if not lines and line == "!!":
            lines.append("!!")
            break
        elif line.startswith("//"):
            continue
        else:
            command_complete = line.strip().endswith(";")
            if command_complete:
                line = line.strip()[:-1]
            lines.append(line)
    return " ".join(lines).strip()
