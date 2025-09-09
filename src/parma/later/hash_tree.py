import os
import hashlib
import json
from pathlib import Path

def sha1_of_file(filepath):
    """Compute SHA-1 hash of a file."""
    h = hashlib.sha1()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def hash_directory(path):
    """Recursively hash files and build dict for a directory."""
    result = {}
    for entry in sorted(os.listdir(path)):
        full_path = os.path.join(path, entry)
        if os.path.isfile(full_path):
            result[entry] = sha1_of_file(full_path)
        elif os.path.isdir(full_path):
            result[entry] = hash_directory(full_path)
    return result

if __name__ == "__main__":
    root = "src"
    tree_hashes = hash_directory(root)
    print(json.dumps(tree_hashes, indent=2))