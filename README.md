# FenceGuard Lite

A real-time fencing motion and head-impact monitor for Traumatic Brain Injury (TBI) research. FenceGuard Lite features an autonomous virtual PTZ camera, skeleton overlay, joint angle analysis, and event detection including a prototype Fencing Response indicator.

## Architecture

FenceGuard Lite uses a polyglot architecture:
- **Gateway (Java 17 + Spring Boot)**: Handles all security, API routing, WebSocket relay, and file uploads. It is the only public-facing service.
- **CV Worker (Python 3.11)**: Runs the YOLOv8n object detection, MediaPipe Pose estimation, virtual PTZ, biomechanics engine, and event detection. Exposes a localhost-only gRPC stream.

## Quick Start (Docker)

The easiest way to run the application is using Docker Compose.

1. Clone the repository.
2. Ensure you have Docker and Docker Compose installed.
3. Run the following command from the root directory:
   ```bash
   docker compose up --build
   ```
4. Open your browser and navigate to `http://127.0.0.1:8080`.
5. Enter the default API key: `fenceguard-secure-demo-key-2026`
6. Click **Upload Video** and select a fencing video clip to start analyzing!

## Manual Setup (Windows)

If you prefer to run the services manually without Docker:

### Prerequisites
- JDK 17+
- Python 3.11
- A valid video file (or use a webcam)

### 1. Start the CV Worker (Python)
```powershell
cd cv-worker
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# Generate gRPC stubs
mkdir generated
python -m grpc_tools.protoc -I../proto --python_out=generated --grpc_python_out=generated ../proto/fenceguard.proto

python server.py
```

### 2. Start the Gateway (Java)
In a new terminal:
```powershell
cd gateway
# The project uses Gradle. Ensure Gradle is installed or use the wrapper if provided.
gradle build -x test
java -jar build/libs/fenceguard-gateway-1.0.0.jar
```

3. Open `http://127.0.0.1:8080` in your browser.

## Security Features

- **API Key Authentication**: Required for all `/api/*` and WebSocket connections. Validated using constant-time comparison.
- **Strict File Uploads**: Validated by extension and Apache Tika magic bytes. Enforced size limits and UUID filename renaming to prevent path traversal.
- **Internal gRPC Authentication**: The CV worker validates an internal token on every RPC to ensure only the gateway can communicate with it.
- **Security Headers**: Strict Content-Security-Policy (CSP), CORS limited to localhost, nosniff, and X-Frame-Options DENY.
