import sys
import os
import pytest

import intern.dbc as dbc
import intern.helper as h


# Test case for validating node_instance
def test_node_instance():
    node_instance = {
        "name": "concat_node",
        "image": {"name": "concat_node", "version": "latest"},
        "input": {
            "i1": {"type": "file", "format": "any", "path_in_container": "/data/f1.txt"},
            "i2": {"type": "file", "format": "any", "path_in_container": "/data/f2.txt"}
        },
        "output": {
            "o": {"type": "file", "format": "any", "path_in_container": "/data/f3.txt"}
        }
    }
    try:
        h.validate_user_input(node_instance, "node_def")
    except dbc.ParmaException as e:
        pytest.fail(f"Validation failed: {e}")
    node_instance = {
        "name": "concat_node",
        "image": {"name": "concat_node", "version": "latest"},
        "input": {
            "i1": {"type": "file", "format": "any", "qay": "/data/f1.txt"},
            "i2": {"type": "file", "format": "any", "path_in_container": "/data/f2.txt"}
        },
        "output": {
            "o": {"type": "file", "format": "any", "path_in_container": "/data/f3.txt"}
        }
    }
    try:
        h.validate_user_input(node_instance, "node_def")
        pytest.fail(f"Validation succeeded but should have failed")
    except dbc.ParmaException as e:
        pass
