#!/bin/bash

# Define the input and output file paths
base="/data"
input_file1="$base/f1.txt"
input_file2="$base/f2.txt"
output_file="$base/f3.txt"

# Check if the input is ok
if [[ ! -f "$input_file1" ]]; then
    echo "Error: $input_file1 does not exist."
    exit 12
fi

if [[ ! -f "$input_file2" ]]; then
    echo "Error: $input_file2 does not exist."
    exit 12
fi

raw_cmd="${CMD:-}"
echo "debug of CMD: '$raw_cmd'"

# Check if the environment variable is a number
if [[ "$raw_cmd" =~ ^[0-9]+$ ]]; then
    repeat=$((raw_cmd))
else
    repeat=1
fi

# Concatenate the files and write the result to the output file
for ((i=1; i<=repeat; i++)); do
    ( cat "$input_file1"; echo ''; cat "$input_file2"; echo '' ) >> "$output_file"
done

echo "Files $input_file1 and $input_file2 concatenated successfully."
echo "Repeat: $repeat."
echo "Output written to $output_file."