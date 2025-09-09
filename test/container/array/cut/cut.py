import os
import json

input_file = "/data/input_array.json"
output_file = "/data/output_array.json"

cut = os.environ.get("DIR", "left")
count = int(os.environ.get("COUNT", "1"))

try:
    with open(input_file, "r") as f:
        array = json.load(f)
except FileNotFoundError:
    print(f"Input file does not exist. Output will be an empty array.")
    array = []
except json.JSONDecodeError:
    print(f"Input file is not valid JSON. Output will be an empty array.")
    array = []

if not isinstance(array, list):
    print("Input file must contain a JSON array. Input copied to output")
elif cut == "left":
    array = array[count:] if count > 0 else array
elif cut == "right":
    array = array[:-count] if count > 0 else array
else:
    print("CUT must be 'left' or 'right'. Input copied to output")

try:
    with open(output_file, "w") as f:
        json.dump(array, f)
except Exception:
    print("Output file could not be written")