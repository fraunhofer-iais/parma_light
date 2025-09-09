#!/bin/bash

output_file="/data/generated_array.json"

# Validate COUNT is set and is a positive integer
if ! [[ "$COUNT" =~ ^[0-9]+$ ]] || [ -z "$COUNT" ]; then
  COUNT=10  # Default value
fi

# Generate JSON array
json="["
for ((i=1; i<=COUNT; i++)); do
  json+="$i"
  if [ "$i" -lt "$COUNT" ]; then
    json+=","
  fi
done
json+="]"

# Write to output file
echo "$json" > "$output_file"

echo "JSON array 1...$COUNT written to $output_file."