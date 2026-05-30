import argparse
import json

output_file = "/data/generated_array.json"

# Read and validate the parameter --count
parser = argparse.ArgumentParser(description="generate the JSON array 1...count")
parser.add_argument("--count", type=int, default=10, help="number of elements (default 10)")
count = parser.parse_args().count
if count < 1:
    count = 10  # Default value

# Generate JSON array from 1 to count
numbers = list(range(1, count + 1))

# Write to output file
with open(output_file, "w") as f:
    json.dump(numbers, f)

print(f"JSON array 1...{count} written to {output_file}.")
