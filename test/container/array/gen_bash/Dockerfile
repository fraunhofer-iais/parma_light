# Use a lightweight base image
FROM alpine:latest

# Install necessary tools
RUN apk add --no-cache bash

COPY gen_array.sh /gen_array.sh
RUN chmod +x /gen_array.sh
ENTRYPOINT ["/gen_array.sh"]