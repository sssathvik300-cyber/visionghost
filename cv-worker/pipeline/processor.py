"""
Full frame pipeline orchestrator.

Reads frames from a video source (webcam or file), runs the complete
CV + analytics pipeline, and yields processed FrameData for gRPC streaming.
"""

import cv2
import json
import time
import numpy as np
import logging

from .detect_track import PersonDetector
from .pose import PoseEstimator
from .ptz_controller import PTZController
from .biomechanics import BiomechanicsEngine
from .events import EventDetector

logger = logging.getLogger(__name__)


class FrameProcessor:
    """
    Orchestrates the full per-frame pipeline:
    1. Read frame from VideoCapture
    2. YOLO detect → select target
    3. MediaPipe Pose → 33 landmarks
    4. PTZ controller → broadcast + inset frames
    5. Biomechanics → joint angles + head kinematics
    6. Event detection → lunge, impact, fencing response
    7. Draw overlays
    8. Encode frames as JPEG
    """

    def __init__(self, config: dict):
        self.config = config
        self.detector = PersonDetector(config)
        self.pose = PoseEstimator(config)
        self.ptz = PTZController(config)
        self.biomechanics = BiomechanicsEngine(config)
        self.events = EventDetector(config)

        cam_cfg = config.get('camera', {})
        self.frame_width = cam_cfg.get('frame_width', 640)
        self.fps_cap = cam_cfg.get('fps_cap', 30)
        self.jpeg_quality = cam_cfg.get('jpeg_quality', 85)

        self._cap = None
        self._running = False
        self._frame_id = 0
        self._start_time = 0.0

    def open_source(self, source: str) -> bool:
        """Open a video source (webcam index or file path)."""
        if source == "webcam" or source == "0":
            self._cap = cv2.VideoCapture(0)
        else:
            self._cap = cv2.VideoCapture(source)

        if not self._cap.isOpened():
            logger.error("Failed to open video source: %s", source)
            return False

        logger.info("Video source opened: %s (%.0fx%.0f @ %.1f fps)",
                     source,
                     self._cap.get(cv2.CAP_PROP_FRAME_WIDTH),
                     self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
                     self._cap.get(cv2.CAP_PROP_FPS))

        self._running = True
        self._frame_id = 0
        self._start_time = time.time()
        return True

    def process_frames(self):
        """
        Generator that yields processed frame data dicts.
        Each yield contains: jpeg_frame, inset_frame, metrics_json, events_json
        """
        if self._cap is None or not self._running:
            return

        min_frame_time = 1.0 / self.fps_cap
        prev_time = time.time()

        while self._running:
            frame_start = time.time()

            ret, frame = self._cap.read()
            if not ret:
                logger.info("Video source ended (frame %d)", self._frame_id)
                break

            self._frame_id += 1
            current_time = time.time()
            dt = current_time - prev_time
            prev_time = current_time

            # Downscale for performance
            h, w = frame.shape[:2]
            if w > self.frame_width:
                scale = self.frame_width / w
                frame = cv2.resize(frame, None, fx=scale, fy=scale,
                                    interpolation=cv2.INTER_LINEAR)

            # ── 1. YOLO detection ────────────────────────
            target = self.detector.detect(frame)
            bbox = target.bbox if target.is_valid else None

            # ── 2. MediaPipe Pose ────────────────────────
            landmarks = self.pose.estimate(frame, bbox)

            # ── 3. Biomechanics ──────────────────────────
            elapsed = current_time - self._start_time
            metrics = self.biomechanics.compute(landmarks, elapsed, dt)

            # ── 4. Event detection ───────────────────────
            events = self.events.detect(landmarks, metrics, elapsed, dt)

            # ── 5. Draw overlays on frame ────────────────
            annotated = self.pose.draw_skeleton(frame, landmarks)
            if bbox and target.is_valid:
                annotated = self._draw_bbox(annotated, bbox, target.confidence)

            # ── 6. PTZ controller ────────────────────────
            ptz_result = self.ptz.update(annotated, bbox, landmarks)

            # ── 7. Encode frames ─────────────────────────
            ptz_frame = ptz_result['ptz_frame']
            inset_frame = ptz_result['inset_frame']

            # Resize inset to be small
            inset_h = int(inset_frame.shape[0] * 0.3)
            inset_w = int(inset_frame.shape[1] * 0.3)
            inset_small = cv2.resize(inset_frame, (inset_w, inset_h))

            _, ptz_jpeg = cv2.imencode('.jpg', ptz_frame,
                                        [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
            _, inset_jpeg = cv2.imencode('.jpg', inset_small,
                                          [cv2.IMWRITE_JPEG_QUALITY, 70])

            # ── 8. Compute FPS ───────────────────────────
            frame_time = time.time() - frame_start
            fps = 1.0 / frame_time if frame_time > 0 else 0

            # Add PTZ info to metrics
            metrics['ptz'] = {
                'zoom_level': ptz_result['zoom_level'],
                'crop_rect': ptz_result['crop_rect'],
            }
            metrics['tracking'] = {
                'confidence': round(target.confidence, 3) if target.is_valid else 0,
                'bbox': [round(v, 1) for v in bbox] if bbox else None,
            }

            yield {
                'jpeg_frame': ptz_jpeg.tobytes(),
                'inset_frame': inset_jpeg.tobytes(),
                'metrics_json': json.dumps(metrics),
                'events_json': json.dumps(events),
                'frame_id': self._frame_id,
                'timestamp': elapsed,
                'fps': round(fps, 1),
            }

            # FPS cap
            elapsed_frame = time.time() - frame_start
            if elapsed_frame < min_frame_time:
                time.sleep(min_frame_time - elapsed_frame)

    def stop(self):
        """Stop processing and release resources."""
        self._running = False
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self.pose.close()
        logger.info("Processor stopped after %d frames", self._frame_id)

    def _draw_bbox(self, frame: np.ndarray, bbox: list[float],
                    confidence: float) -> np.ndarray:
        """Draw target bounding box with confidence label."""
        x1, y1, x2, y2 = [int(v) for v in bbox]
        color = (255, 180, 0)  # Cyan

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)

        label = f"Fencer {confidence:.0%}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
        cv2.putText(frame, label, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

        return frame
