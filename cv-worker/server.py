"""
FenceGuard Lite — Python CV Worker gRPC Server

Binds to 127.0.0.1 only (never network-exposed).
Validates internal token on every RPC.
Streams annotated JPEG frames + event JSON to the Java gateway.
"""

import os
import sys
import signal
import logging
import yaml
import grpc
from concurrent import futures

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline.processor import FrameProcessor

# ── Generate / import protobuf stubs ─────────────────────
# These are generated from proto/fenceguard.proto
# Run: python -m grpc_tools.protoc -I../proto --python_out=generated --grpc_python_out=generated ../proto/fenceguard.proto
GENERATED_DIR = os.path.join(os.path.dirname(__file__), 'generated')
sys.path.insert(0, GENERATED_DIR)

try:
    import fenceguard_pb2
    import fenceguard_pb2_grpc
except ImportError:
    print("ERROR: gRPC stubs not found. Generate them first:")
    print("  cd cv-worker")
    print("  python -m grpc_tools.protoc -I../proto --python_out=generated --grpc_python_out=generated ../proto/fenceguard.proto")
    sys.exit(1)

# ── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('fenceguard.cv-worker')


class CvWorkerServicer(fenceguard_pb2_grpc.CvWorkerServicer):
    """gRPC service implementation for the CV pipeline."""

    def __init__(self, config: dict, internal_token: str):
        self.config = config
        self.internal_token = internal_token
        self.active_processors: dict[str, FrameProcessor] = {}

    def StreamSession(self, request, context):
        """
        Server-streaming RPC: process video frames and stream results.
        """
        # Validate internal token
        if request.internal_token != self.internal_token:
            context.abort(grpc.StatusCode.UNAUTHENTICATED,
                          "Invalid internal token")
            return

        session_id = request.session_id
        source = request.source
        logger.info("StreamSession started: session=%s, source=%s",
                     session_id, source)

        processor = FrameProcessor(self.config)
        self.active_processors[session_id] = processor

        try:
            if not processor.open_source(source):
                context.abort(grpc.StatusCode.NOT_FOUND,
                              f"Cannot open video source: {source}")
                return

            for frame_data in processor.process_frames():
                if not context.is_active():
                    logger.info("Client disconnected for session %s", session_id)
                    break

                yield fenceguard_pb2.FrameData(
                    jpeg_frame=frame_data['jpeg_frame'],
                    inset_frame=frame_data['inset_frame'],
                    metrics_json=frame_data['metrics_json'],
                    events_json=frame_data['events_json'],
                    frame_id=frame_data['frame_id'],
                    timestamp=frame_data['timestamp'],
                    fps=frame_data['fps'],
                )

        except Exception as e:
            logger.error("Error in StreamSession %s: %s", session_id, e)
            context.abort(grpc.StatusCode.INTERNAL, str(e))

        finally:
            processor.stop()
            self.active_processors.pop(session_id, None)
            logger.info("StreamSession ended: session=%s", session_id)

    def StopSession(self, request, context):
        """Stop an active processing session."""
        session_id = request.session_id
        processor = self.active_processors.get(session_id)

        if processor:
            processor.stop()
            self.active_processors.pop(session_id, None)
            logger.info("Session stopped: %s", session_id)
            return fenceguard_pb2.StopResponse(success=True,
                                                message="Session stopped")
        else:
            return fenceguard_pb2.StopResponse(success=False,
                                                message="Session not found")


def load_config() -> dict:
    """Load configuration from config.yaml."""
    config_path = os.path.join(os.path.dirname(__file__), 'config.yaml')
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    logger.warning("config.yaml not found, using defaults")
    return {}


def serve():
    """Start the gRPC server."""
    config = load_config()
    grpc_cfg = config.get('grpc', {})
    
    # Read from environment first (for Docker), fallback to config, then 127.0.0.1
    host = os.environ.get('FENCEGUARD_GRPC_HOST', grpc_cfg.get('host', '127.0.0.1'))
    port = grpc_cfg.get('port', 50051)

    # Internal token from environment
    internal_token = os.environ.get(
        'FENCEGUARD_INTERNAL_TOKEN', 'changeme-internal-grpc-token')

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=4),
        options=[
            ('grpc.max_send_message_length', 16 * 1024 * 1024),
            ('grpc.max_receive_message_length', 16 * 1024 * 1024),
        ]
    )

    servicer = CvWorkerServicer(config, internal_token)
    fenceguard_pb2_grpc.add_CvWorkerServicer_to_server(servicer, server)

    bind_address = f"{host}:{port}"
    server.add_insecure_port(bind_address)

    # Graceful shutdown
    def handle_signal(signum, frame):
        logger.info("Shutdown signal received, stopping...")
        for proc in servicer.active_processors.values():
            proc.stop()
        server.stop(5)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    server.start()
    logger.info("CV Worker gRPC server started on %s", bind_address)
    logger.info("Waiting for connections from gateway...")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt, shutting down...")
        server.stop(5)


if __name__ == '__main__':
    serve()
