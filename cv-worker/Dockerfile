FROM python:3.11-slim

# Install system dependencies for OpenCV and gRPC
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -s /bin/bash fenceguard
WORKDIR /app
RUN chown fenceguard:fenceguard /app

# Copy requirements
COPY --chown=fenceguard:fenceguard cv-worker/requirements.txt /app/cv-worker/

# Install python dependencies globally as root
RUN pip install --no-cache-dir -r /app/cv-worker/requirements.txt

# Switch to non-root user
USER fenceguard

# Copy files with proper ownership
COPY --chown=fenceguard:fenceguard proto /app/proto
COPY --chown=fenceguard:fenceguard cv-worker /app/cv-worker

WORKDIR /app/cv-worker

# Generate gRPC stubs
RUN mkdir -p generated && \
    python -m grpc_tools.protoc -I../proto --python_out=generated --grpc_python_out=generated ../proto/fenceguard.proto

ENTRYPOINT ["python", "server.py"]
