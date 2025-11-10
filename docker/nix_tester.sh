#!/bin/bash

echo "uri of nix call: $1"
echo "hash of nix call: $2"

if [[ $1 == 'gen-uri' ]]
then
    echo "value of env var 'STRING' is '$STRING'. To be written into a file."
    echo "output file defined in env var 'FILE' is: $FILE"

    echo "START"
    echo "$STRING" >$FILE
    echo "DONE"
elif [[ $1 == 'repeat-uri' ]]
then
    echo "value of env var 'COUNT' defines how often the input is repeated: $COUNT"
    echo "input file defined in env var 'INPUT_FILE' is: $INPUT_FILE"
    echo "output file defined in env var 'OUTPUT_FILE' is: $OUTPUT_FILE"

    echo "START"
    CONTENT=$(cat $INPUT_FILE)
    for i in $(seq 1 $COUNT);
    do
        echo $CONTENT >>$OUTPUT_FILE
    done
    echo "DONE"
else
    echo "invalid uri: '$uri'"
    exit 12
fi