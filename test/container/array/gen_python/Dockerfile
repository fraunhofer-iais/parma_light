# Use a Python base image
FROM python:3.13-slim

# Set the working directory
WORKDIR /app

# Copy the Python script into the container, set the entrypoint to run the script
COPY gen_array.py .
CMD ["python", "gen_array.py"]