"""
YOLOv8n person detection + simple target tracking.

Detects all persons in each frame, selects the primary fencer
(largest, most central), and maintains identity across frames
using IoU + centroid matching.
"""

import numpy as np
import logging

logger = logging.getLogger(__name__)

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    logger.warning("ultralytics not installed — detection disabled")

try:
    import torch
    CUDA_AVAILABLE = torch.cuda.is_available()
except ImportError:
    CUDA_AVAILABLE = False


class Detection:
    """A single person detection."""
    __slots__ = ('bbox', 'confidence', 'center', 'area')

    def __init__(self, bbox: list[float], confidence: float):
        self.bbox = bbox  # [x1, y1, x2, y2]
        self.confidence = confidence
        self.center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
        self.area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])


class TrackedTarget:
    """Maintains identity of the primary target across frames."""

    def __init__(self):
        self.bbox = None
        self.center = None
        self.confidence = 0.0
        self.frames_lost = 0
        self.max_lost_frames = 15

    def update(self, detection: Detection | None):
        if detection is not None:
            self.bbox = detection.bbox
            self.center = detection.center
            self.confidence = detection.confidence
            self.frames_lost = 0
        else:
            self.frames_lost += 1

    @property
    def is_valid(self) -> bool:
        return self.bbox is not None and self.frames_lost < self.max_lost_frames


class PersonDetector:
    """
    YOLOv8n person detector with target selection and tracking.

    - Detects all persons in the frame
    - Selects the largest, most central person as the primary target
    - Maintains frame-to-frame identity via IoU matching
    """

    PERSON_CLASS_ID = 0

    def __init__(self, config: dict):
        self.config = config
        model_cfg = config.get('models', {}).get('yolo', {})
        self.model_path = model_cfg.get('model_path', 'yolov8n.pt')
        self.confidence = model_cfg.get('confidence', 0.5)
        self.iou_threshold = model_cfg.get('iou_threshold', 0.45)

        # Determine device
        device_cfg = model_cfg.get('device', 'auto')
        if device_cfg == 'auto':
            self.device = 'cuda' if CUDA_AVAILABLE else 'cpu'
        else:
            self.device = device_cfg

        self.model = None
        self.target = TrackedTarget()
        self.frame_width = config.get('camera', {}).get('frame_width', 640)

        if YOLO_AVAILABLE:
            logger.info("Loading YOLO model: %s (device: %s)", self.model_path, self.device)
            self.model = YOLO(self.model_path)
        else:
            logger.warning("YOLO not available — using dummy detections")

    def detect(self, frame: np.ndarray) -> TrackedTarget:
        """
        Detect persons in the frame and return the tracked primary target.
        """
        if self.model is None:
            return self._dummy_target(frame)

        h, w = frame.shape[:2]

        # Run YOLO inference
        results = self.model.predict(
            frame,
            conf=self.confidence,
            iou=self.iou_threshold,
            classes=[self.PERSON_CLASS_ID],
            device=self.device,
            imgsz=self.frame_width,
            verbose=False
        )

        detections = []
        if results and len(results) > 0:
            boxes = results[0].boxes
            if boxes is not None:
                for i in range(len(boxes)):
                    bbox = boxes.xyxy[i].cpu().numpy().tolist()
                    conf = float(boxes.conf[i].cpu().numpy())
                    detections.append(Detection(bbox, conf))

        # Select primary target
        best = self._select_target(detections, w, h)
        self.target.update(best)

        return self.target

    def _select_target(self, detections: list[Detection],
                        frame_w: int, frame_h: int) -> Detection | None:
        """
        Select the best target: largest + most central person.
        If we have an existing target, prefer the detection with highest IoU.
        """
        if not detections:
            return None

        if self.target.is_valid and self.target.bbox is not None:
            # Match by IoU to existing target
            best_iou = 0.0
            best_det = None
            for det in detections:
                iou = self._compute_iou(self.target.bbox, det.bbox)
                if iou > best_iou:
                    best_iou = iou
                    best_det = det
            if best_iou > 0.3:
                return best_det

        # No existing target or no match — pick largest + most central
        frame_cx = frame_w / 2
        frame_cy = frame_h / 2
        max_area = max(d.area for d in detections) if detections else 1.0

        best_score = -1
        best_det = None
        for det in detections:
            # Score = area_ratio * (1 - distance_from_center_ratio)
            area_score = det.area / max_area
            dist = ((det.center[0] - frame_cx) ** 2 +
                    (det.center[1] - frame_cy) ** 2) ** 0.5
            max_dist = (frame_cx ** 2 + frame_cy ** 2) ** 0.5
            center_score = 1.0 - (dist / max_dist) if max_dist > 0 else 0.5

            score = 0.6 * area_score + 0.4 * center_score
            if score > best_score:
                best_score = score
                best_det = det

        return best_det

    @staticmethod
    def _compute_iou(box1: list[float], box2: list[float]) -> float:
        """Compute Intersection over Union between two bounding boxes."""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])

        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - inter

        return inter / union if union > 0 else 0.0

    def _dummy_target(self, frame: np.ndarray) -> TrackedTarget:
        """Fallback target when YOLO is not available — center of frame."""
        h, w = frame.shape[:2]
        margin = 0.2
        dummy = Detection(
            [w * margin, h * margin, w * (1 - margin), h * (1 - margin)],
            confidence=0.5
        )
        self.target.update(dummy)
        return self.target
