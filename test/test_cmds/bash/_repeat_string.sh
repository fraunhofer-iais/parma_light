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