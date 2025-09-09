import re

# Regular expression pattern for valid names
pattern_valid_name = re.compile(r"^[a-zA-Z0-9_]+$")


class ParmaException(Exception):
    """
    Custom exception class for handling user and system errors.

    Attributes:
        error_description (dict): The description of the error.
    """

    def __init__(self, error_description: dict):
        super().__init__(error_description)
        self.error_description: dict = error_description

    def __str__(self) -> str:
        return f"ParmaException: {self.error_description}"


def raise_error(error_description: dict, user_error: bool = True) -> None:
    """
    Raise a user-related or system error.

    Args:
        error_description (dict): A dictionary containing details about the error.
        user_error (bool, optional): True for user errors, False for system errors. Default is True.

    Raises:
        ParmaException: Always raises a ParmaException with the provided description.
    """
    error_description["category"] = "USER_ERROR" if user_error else "SYSTEM_ERROR"
    raise ParmaException(error_description)


def assert_true(condition: bool, error_description: dict, user_error: bool = True) -> None:
    """
    Assert a condition for user-related logic. Raise a user or system error if the condition is False.

    Args:
        condition (bool): The condition to assert.
        error_description (dict): A dictionary containing details about the error.
        user_error (bool, optional): True for user errors, False for system (programming) errors. Default is True.

    Raises:
        ParmaException: If the condition is False.
    """
    if not condition:
        raise_error(error_description, user_error)

