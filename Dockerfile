# Stage 1: Build stage
FROM python:3.9-slim AS builder

WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt


# Stage 2: Final image
FROM python:3.9-slim

WORKDIR /app

# Install production system dependencies, including PostgreSQL client
RUN apt-get update && apt-get install -y \
    libpq5 \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy pre-built wheels and install them
COPY --from=builder /app/wheels /app/wheels
COPY --from=builder /app/requirements.txt .
RUN pip install --no-cache /app/wheels/*

# Copy application code
COPY app/ ./app/

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]