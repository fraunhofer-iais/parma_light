#!/bin/bash

# Define the input and output paths
input_dir="/data/dir_in"
output_dir="/data/dir_out"

# Check if the input is ok
if [[ ! -d "$input_dir" ]]; then
    echo "Error: $input_dir must be a directory."
    exit 12
fi

# copy the files
cp $input_dir/* $output_dir

echo "Files from directory $input_dir successfully copied to directory $output_dir."