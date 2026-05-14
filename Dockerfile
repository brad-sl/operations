FROM python:3.12-alpine

# Install system dependencies
RUN apk add --no-cache \
    postgresql-client \
    build-base \
    postgresql-dev \
    && rm -rf /var/cache/apk/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Make entrypoint executable
RUN chmod +x entrypoint.sh

EXPOSE 8000
