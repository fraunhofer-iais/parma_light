echo "value of env var 'STRING' is '$STRING'. To be written into a file."
echo "output file defined in env var 'FILE' is: $FILE"

echo "START"
echo "$STRING" >$FILE
echo "DONE"