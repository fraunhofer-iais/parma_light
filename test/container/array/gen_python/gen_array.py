import os
import sys
import json

output_file = "/data/generated_array.json"

# Read and validate COUNT environment variable
count_env = os.getenv("COUNT")
try:
    count = int(count_env)
    if count < 1:
        raise ValueError
except (TypeError, ValueError):
    count = 10  # Default value

# Generate JSON array from 1 to COUNT
numbers = list(range(1, count + 1))

# Write to output file
with open(output_file, "w") as f:
    json.dump(numbers, f)

print(f"JSON array 1...{count} written to {output_file}.")