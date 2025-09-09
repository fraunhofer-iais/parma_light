import json
import os

result = []

for i in range(1, 6):
    filename = f"/data/in_{i}.json"
    if os.path.exists(filename):
        with open(filename, "r") as f:
            arr = json.load(f)
            if isinstance(arr, list):
                result.extend(arr)
            else:
                print(f"Warning: {filename} does not contain a JSON array.")

with open("/data/out.json", "w") as f:
    json.dump(result, f)