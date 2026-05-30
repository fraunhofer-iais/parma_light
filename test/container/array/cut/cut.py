import argparse
import json

input_file = "/data/input_array.json"
output_file = "/data/output_array.json"

parser = argparse.ArgumentParser(description="cut elements from the left or right end of a JSON array")
parser.add_argument("--direction", default="left", help="'left' or 'right': the end to cut from")
parser.add_argument("--count", type=int, default=1, help="number of elements to cut")
args = parser.parse_args()
cut = args.direction
count = args.count

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
    print("--direction must be 'left' or 'right'. Input copied to output")

try:
    with open(output_file, "w") as f:
        json.dump(array, f)
except Exception:
    print("Output file could not be written")
