import sys
import os
import pytest

import intern.dbc as dbc
import intern.helper as h


def validate(instance=None, definition=None, success=True):
    try:
        h.validate_user_input(instance, definition)
        if success:
            pass
        else:
            pytest.fail(f"Validation succeeded but should have failed")
    except dbc.ParmaException as e:
        if success:
            pytest.fail(f"Validation failed with exception: {e}")
        else:
            pass


def test_image_node():
    node_instance = {
        "name": "test_node",
        "image": {"name": "test_image", "version": "latest"},
        "input": {
            "i1": {"type": "file", "format": "any", "path_in_container": "/data/f1.txt"},
            "i2": {"type": "file", "format": "any", "path_in_container": "/data/f2.txt"}
        },
        "output": {
            "o": {"type": "file", "format": "any", "path_in_container": "/data/f3.txt"}
        }
    }
    validate(instance=node_instance, definition="node_def", success=True)

    node_instance = {
        "name": "test_node",
        "image": {"name": "test_image", "version": "latest"},
        "input": {
            "i1": {"type": "file", "format": "any", "qay": "/data/f1.txt"},
            "i2": {"type": "file", "format": "any", "path_in_container": "/data/f2.txt"}
        },
        "output": {
            "o": {"type": "file", "format": "any", "path_in_container": "/data/f3.txt"}
        }
    }
    validate(instance=node_instance, definition="node_def", success=False)

def test_bash_node():
    node_instance = {
        "name": "test_node",
        "bash": {"name": "gen_string", "version": "latest"},
        "input": {
            "i1": {"type": "file", "format": "any", "environment_var_in_container": "F1"},
            "i2": {"type": "file", "format": "any", "environment_var_in_container": "F2"}
        },
        "output": {
            "o": {"type": "file", "format": "any", "environment_var_in_container": "F3"}
        }
    }
    validate(instance=node_instance, definition="node_def", success=True)

    node_instance = {
        "name": "test_node",
        "bash": {"name": "gen_string", "version": "latest"},
        "image": {"name": "test_image", "version": "latest"},
        "input": {
            "i1": {"type": "file", "format": "any", "environment_var_in_container": "F1"},
            "i2": {"type": "file", "format": "any", "environment_var_in_container": "F2"}
        },
        "output": {
            "o": {"type": "file", "format": "any", "environment_var_in_container": "F3"}
        }
    }
    validate(instance=node_instance, definition="node_def", success=False)

def test_nix_node():
    node_instance = {
        "name": "test_node",
        "nix": {"uri": "https://somewhere"},
        "input": {
            "i1": {"type": "file", "format": "any", "environment_var_in_container": "F1"},
            "i2": {"type": "file", "format": "any", "environment_var_in_container": "F2"}
        },
        "output": {
            "o": {"type": "file", "format": "any", "environment_var_in_container": "F3"}
        }
    }
    validate(instance=node_instance, definition="node_def", success=True)

    node_instance = {
        "name": "test_node",
        "nix": {"hash": "some_hash"},
        "input": {
            "i1": {"type": "file", "format": "any", "environment_var_in_container": "F1"},
            "i2": {"type": "file", "format": "any", "environment_var_in_container": "F2"}
        },
        "output": {
            "o": {"type": "file", "format": "any", "environment_var_in_container": "F3"}
        }
    }
    validate(instance=node_instance, definition="node_def", success=True)

    node_instance = {
        "name": "test_node",
        "nix": {"uri": "https://somewhere", "hash": "some_hash"},
        "input": {
            "i1": {"type": "file", "format": "any", "environment_var_in_container": "F1"},
            "i2": {"type": "file", "format": "any", "environment_var_in_container": "F2"}
        },
        "output": {
            "o": {"type": "file", "format": "any", "environment_var_in_container": "F3"}
        }
    }
    validate(instance=node_instance, definition="node_def", success=False)