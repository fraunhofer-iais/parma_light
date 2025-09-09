FROM python:3.13-slim

# Install necessary dependencies and set the working directory
RUN pip install --no-cache-dir scikit-learn
RUN pip install --no-cache-dir numpy
WORKDIR /app

# Copy the Python script into the container, set the default command to run the Python script
COPY sklearn_train.py .
CMD ["python", "sklearn_train.py"]