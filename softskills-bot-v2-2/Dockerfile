FROM python:3.11-slim

# Set workdir
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y build-essential

# Install pip dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app

# Expose port for Render
EXPOSE 8080

# Start server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]