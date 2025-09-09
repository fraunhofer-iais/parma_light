#!/bin/bash

# Define the input and output paths
input_dir="/data/dir_in"
output_file="/data/out"

# Check if the input is ok
if [[ ! -d "$input_dir" ]]; then
    echo "Error: $input_dir must be a directory."
    exit 12
fi

# Concatenate the files and write the result to the output file
files=("$input_dir"/*)
if [[ ${#files[@]} -gt 0 && -e "${files[0]}" ]]; then
  cat "${files[@]}" >$output_file
else
  echo "No files to concatenate in $input_dir." >$output_file
fi

echo "Files from directory $input_dir (if any) concatenated successfully."
echo "Output written to $output_file."