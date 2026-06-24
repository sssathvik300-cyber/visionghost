"""
MediaPipe Pose estimation — 33 anatomical landmarks.

Runs pose detection on the target crop from the YOLO detector,
maps landmarks back to full-frame coordinates, and draws a
clean skeleton overlay with anatomical connections.
"""

import numpy as np
import cv2
import logging

logger = logging.getLogger(__name__)

try:
    import mediapipe as mp
    MP_AVAILABLE = True
except ImportError:
    MP_AVAILABLE = False
    logger.warning("mediapipe not installed — pose estimation disabled")

# MediaPipe Pose landmark names (33 total)
LANDMARK_NAMES = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky",
    "left_index", "right_index", "left_thumb", "right_thumb",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel",
    "left_foot_index", "right_foot_index"
]

# Skeleton connections for drawing
SKELETON_CONNECTIONS = [
    # Torso
    (11, 12), (11, 23), (12, 24), (23, 24),
    # Left arm
    (11, 13), (13, 15),
    # Right arm
    (12, 14), (14, 16),
    # Left leg
    (23, 25), (25, 27), (27, 29), (27, 31),
    # Right leg
    (24, 26), (26, 28), (28, 30), (28, 32),
    # Face
    (0, 7), (0, 8),
]

# Joint colors by visibility
COLOR_VISIBLE = (0, 255, 100)     # Green
COLOR_PARTIAL = (0, 220, 255)     # Yellow
COLOR_OCCLUDED = (0, 80, 255)     # Red
COLOR_BONE = (220, 180, 80)       # Light blue for bones


class Landmark:
    """A single pose landmark with full-frame coordinates."""
    __slots__ = ('id', 'name', 'x', 'y', 'z', 'visibility')

    def __init__(self, idx: int, x: float, y: float, z: float, visibility: float):
        self.id = idx
        self.name = LANDMARK_NAMES[idx] if idx < len(LANDMARK_NAMES) else f"point_{idx}"
        self.x = x  # Full-frame pixel x
        self.y = y  # Full-frame pixel y
        self.z = z  # Depth (relative)
        self.visibility = visibility

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "x": round(self.x, 1), "y": round(self.y, 1),
            "z": round(self.z, 4), "visibility": round(self.visibility, 3)
        }


class PoseEstimator:
    """
    MediaPipe Pose (33 landmarks) with skeleton overlay drawing.
    Runs on the cropped target region and maps coordinates back to full frame.
    """

    def __init__(self, config: dict):
        self.config = config
        pose_cfg = config.get('models', {}).get('pose', {})
        self.model_complexity = pose_cfg.get('model_complexity', 1)
        self.min_detection_conf = pose_cfg.get('min_detection_confidence', 0.5)
        self.min_tracking_conf = pose_cfg.get('min_tracking_confidence', 0.5)
        self.pose = None

        if MP_AVAILABLE:
            self.mp_pose = mp.solutions.pose
            self.pose = self.mp_pose.Pose(
                static_image_mode=False,
                model_complexity=self.model_complexity,
                min_detection_confidence=self.min_detection_conf,
                min_tracking_confidence=self.min_tracking_conf
            )
            logger.info("MediaPipe Pose initialized (complexity=%d)", self.model_complexity)
        else:
            logger.warning("MediaPipe not available — using dummy landmarks")

    def estimate(self, frame: np.ndarray, bbox: list[float] | None
                  ) -> list[Landmark]:
        """
        Run pose estimation on the target region.

        Args:
            frame: Full frame (BGR)
            bbox: Target bounding box [x1, y1, x2, y2] or None

        Returns:
            List of 33 Landmarks with full-frame coordinates
        """
        if self.pose is None or bbox is None:
            return []

        h, w = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]

        # Add padding around bbox for better pose detection
        pad_x = int((x2 - x1) * 0.15)
        pad_y = int((y2 - y1) * 0.10)
        cx1 = max(0, x1 - pad_x)
        cy1 = max(0, y1 - pad_y)
        cx2 = min(w, x2 + pad_x)
        cy2 = min(h, y2 + pad_y)

        # Crop and convert to RGB for MediaPipe
        crop = frame[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            return []

        rgb_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        results = self.pose.process(rgb_crop)

        if not results.pose_landmarks:
            return []

        # Map landmarks back to full-frame coordinates
        crop_h, crop_w = crop.shape[:2]
        landmarks = []
        for idx, lm in enumerate(results.pose_landmarks.landmark):
            fx = cx1 + lm.x * crop_w
            fy = cy1 + lm.y * crop_h
            landmarks.append(Landmark(idx, fx, fy, lm.z, lm.visibility))

        return landmarks

    def draw_skeleton(self, frame: np.ndarray, landmarks: list[Landmark],
                       thickness: int = 2) -> np.ndarray:
        """
        Draw a clean anatomical skeleton overlay on the frame.
        Color-codes joints by visibility level.
        """
        if not landmarks:
            return frame

        output = frame.copy()

        # Draw bones first (connections)
        for i, j in SKELETON_CONNECTIONS:
            if i >= len(landmarks) or j >= len(landmarks):
                continue
            lm_i, lm_j = landmarks[i], landmarks[j]
            if lm_i.visibility < 0.3 or lm_j.visibility < 0.3:
                continue
            pt1 = (int(lm_i.x), int(lm_i.y))
            pt2 = (int(lm_j.x), int(lm_j.y))
            cv2.line(output, pt1, pt2, COLOR_BONE, thickness, cv2.LINE_AA)

        # Draw joints
        for lm in landmarks:
            if lm.visibility < 0.2:
                continue
            pt = (int(lm.x), int(lm.y))
            if lm.visibility > 0.7:
                color = COLOR_VISIBLE
                radius = 4
            elif lm.visibility > 0.3:
                color = COLOR_PARTIAL
                radius = 3
            else:
                color = COLOR_OCCLUDED
                radius = 2
            cv2.circle(output, pt, radius, color, -1, cv2.LINE_AA)
            cv2.circle(output, pt, radius + 1, (0, 0, 0), 1, cv2.LINE_AA)

        return output

    def close(self):
        """Release MediaPipe resources."""
        if self.pose:
            self.pose.close()
