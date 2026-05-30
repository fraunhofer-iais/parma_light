FROM python:3.13-slim

# Install necessary dependencies and set the working directory
RUN pip install --no-cache-dir scikit-learn
RUN pip install --no-cache-dir numpy
WORKDIR /app

# Copy the Python script into the container. ENTRYPOINT (not CMD), because arguments
# of "docker run <image> --seed 42" must be appended to the command, not replace it
COPY sklearn_train.py .
ENTRYPOINT ["python", "sklearn_train.py"]