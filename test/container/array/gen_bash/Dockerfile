# Use a lightweight base image
FROM alpine:latest

# Install necessary tools
RUN apk add --no-cache bash

# Copy the bash script into the container
COPY gen_array.sh /gen_array.sh

# Make the script executable
RUN chmod +x /gen_array.sh

# Set the entrypoint to the bash script
ENTRYPOINT ["/gen_array.sh"]