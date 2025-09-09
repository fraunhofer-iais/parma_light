# Use a lightweight base image
FROM alpine:latest

# Install necessary tools
RUN apk add --no-cache bash

# Copy the bash script into the container
COPY concat.sh /concat.sh

# Make the script executable
RUN chmod +x /concat.sh

# Set the entrypoint to the bash script
ENTRYPOINT ["/concat.sh"]