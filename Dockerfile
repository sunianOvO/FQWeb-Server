# Use Python base image
FROM python:3.8-slim

# Set working directory
WORKDIR /app

# Copy the server files into the container
COPY server.py /app/server.py

# Copy the requirements file into the container
COPY requirements.txt /app/requirements.txt

# Install required packages
RUN pip install -r requirements.txt

# Expose the server port (make sure it matches the port in server.py)
EXPOSE 5000

# Run the server script
CMD ["python", "server.py"]