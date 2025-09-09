# Use a Python base image
FROM python:3.13-slim

# Set the working directory
WORKDIR /app

# Copy the Python script into the container, set the default command to run the Python script
COPY cut.py .
CMD ["python", "cut.py"]