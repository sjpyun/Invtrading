# Use a slim base image to reduce image size
FROM python:3.12-slim-buster

# Set the working directory inside the container
WORKDIR /app

# Copy requirements.txt first to optimize caching
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . /app
 
# Make port 8080 available to the world outside this container
EXPOSE 8080

# Define environment variable
ENV PORT=8080

# Define the command to run when starting the container
CMD ["gunicorn", "--bind", ":8080", "server:app"] # Assuming your app object is in main.py,  adjust as needed.