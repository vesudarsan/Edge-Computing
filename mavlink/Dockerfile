# Base image with Python
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy files
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt


# Expose Flask port
EXPOSE 5002

# Prevent output buffering
ENV PYTHONUNBUFFERED=1

# Run the app
CMD ["python", "app.py"]
