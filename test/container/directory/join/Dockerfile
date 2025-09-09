# Use a lightweight base image
FROM alpine:latest

# Install necessary tools
RUN apk add --no-cache bash

# Copy the bash script into the container
COPY join.sh /join.sh

# Make the script executable
RUN chmod +x /join.sh

# Set the entrypoint to the bash script
ENTRYPOINT ["/join.sh"]