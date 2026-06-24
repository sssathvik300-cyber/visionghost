"""
Biomechanics engine — clinical joint angles and head kinematics.

Computes per-frame:
- Joint angles (degrees): elbow, knee, torso lean
- Head kinematics: head linear speed (normalized by torso length),
  direction-change rate

All outputs are labeled in clinical units (degrees, normalized speed)
to serve a biomedical engineering audience.
"""

import numpy as np
from collections import deque
import logging

logger = logging.getLogger(__name__)


def _angle_between(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """
    Compute the angle at point b formed by vectors ba and bc.
    Returns angle in degrees [0, 180].
    """
    ba = a - b
    bc = c - b

    cos_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-8)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return float(np.degrees(np.arccos(cos_angle)))


class BiomechanicsEngine:
    """
    Computes clinical biomechanical readouts from pose landmarks.

    Joint angle computation uses the standard three-point method:
    angle at the middle joint formed by the two adjacent segments.
    """

    # Landmark index map for named joints
    JOINTS = {
        'left_shoulder': 11, 'right_shoulder': 12,
        'left_elbow': 13, 'right_elbow': 14,
        'left_wrist': 15, 'right_wrist': 16,
        'left_hip': 23, 'right_hip': 24,
        'left_knee': 25, 'right_knee': 26,
        'left_ankle': 27, 'right_ankle': 28,
        'nose': 0, 'left_ear': 7, 'right_ear': 8,
    }

    def __init__(self, config: dict):
        bio_cfg = config.get('biomechanics', {})
        self.smoothing_window = bio_cfg.get('smoothing_window', 5)
        self.normalize_by_torso = bio_cfg.get('torso_normalization', True)

        # History buffers for smoothing
        self._head_speed_history = deque(maxlen=self.smoothing_window)
        self._prev_head_pos = None
        self._prev_timestamp = None

        # Rolling baseline for head speed (used by event detection)
        self._head_speed_baseline = deque(maxlen=90)  # ~3 seconds at 30fps

    def compute(self, landmarks: list, timestamp: float, dt: float) -> dict:
        """
        Compute all biomechanical metrics for the current frame.

        Returns dict with clinical readouts:
        - joint_angles: {left_elbow, right_elbow, left_knee, right_knee, torso_lean}
        - head_kinematics: {head_speed, head_speed_normalized, direction_change_rate,
                           head_speed_baseline_ratio}
        - torso_length: pixel distance shoulder→hip (for normalization)
        """
        if not landmarks:
            return self._empty_metrics()

        # Build position lookup
        pos = {}
        for lm in landmarks:
            if lm.visibility > 0.3:
                pos[lm.id] = np.array([lm.x, lm.y])

        # ── Joint angles ─────────────────────────────────
        joint_angles = {}

        # Elbow angles (shoulder → elbow → wrist)
        joint_angles['left_elbow'] = self._safe_angle(
            pos, self.JOINTS['left_shoulder'],
            self.JOINTS['left_elbow'], self.JOINTS['left_wrist'])
        joint_angles['right_elbow'] = self._safe_angle(
            pos, self.JOINTS['right_shoulder'],
            self.JOINTS['right_elbow'], self.JOINTS['right_wrist'])

        # Knee angles (hip → knee → ankle)
        joint_angles['left_knee'] = self._safe_angle(
            pos, self.JOINTS['left_hip'],
            self.JOINTS['left_knee'], self.JOINTS['left_ankle'])
        joint_angles['right_knee'] = self._safe_angle(
            pos, self.JOINTS['right_hip'],
            self.JOINTS['right_knee'], self.JOINTS['right_ankle'])

        # Torso lean (deviation of shoulder-hip line from vertical)
        joint_angles['torso_lean'] = self._compute_torso_lean(pos)

        # ── Torso length for normalization ────────────────
        torso_length = self._compute_torso_length(pos)

        # ── Head kinematics ──────────────────────────────
        head_kin = self._compute_head_kinematics(pos, dt, torso_length)

        return {
            'joint_angles': {k: round(v, 1) if v is not None else None
                             for k, v in joint_angles.items()},
            'head_kinematics': head_kin,
            'torso_length': round(torso_length, 1) if torso_length else None,
            'timestamp': timestamp
        }

    def get_head_speed_baseline(self) -> float:
        """Get the rolling baseline head speed (used by event detection)."""
        if len(self._head_speed_baseline) < 5:
            return 1.0  # Default baseline until enough data
        return float(np.mean(self._head_speed_baseline))

    def _safe_angle(self, pos: dict, a_id: int, b_id: int, c_id: int) -> float | None:
        """Compute angle if all three landmarks are available."""
        if a_id in pos and b_id in pos and c_id in pos:
            return _angle_between(pos[a_id], pos[b_id], pos[c_id])
        return None

    def _compute_torso_lean(self, pos: dict) -> float | None:
        """
        Torso lean: angle between the shoulder-hip midline and vertical.
        0° = perfectly upright, positive = leaning forward.
        """
        ls = self.JOINTS['left_shoulder']
        rs = self.JOINTS['right_shoulder']
        lh = self.JOINTS['left_hip']
        rh = self.JOINTS['right_hip']

        if ls in pos and rs in pos and lh in pos and rh in pos:
            shoulder_mid = (pos[ls] + pos[rs]) / 2
            hip_mid = (pos[lh] + pos[rh]) / 2

            # Vector from hip to shoulder
            torso_vec = shoulder_mid - hip_mid
            # Vertical vector (pointing up = negative y in image coords)
            vertical = np.array([0, -1])

            cos_a = np.dot(torso_vec, vertical) / (
                np.linalg.norm(torso_vec) * np.linalg.norm(vertical) + 1e-8)
            cos_a = np.clip(cos_a, -1.0, 1.0)
            return float(np.degrees(np.arccos(cos_a)))

        return None

    def _compute_torso_length(self, pos: dict) -> float | None:
        """Compute pixel distance from shoulder midpoint to hip midpoint."""
        ls = self.JOINTS['left_shoulder']
        rs = self.JOINTS['right_shoulder']
        lh = self.JOINTS['left_hip']
        rh = self.JOINTS['right_hip']

        if ls in pos and rs in pos and lh in pos and rh in pos:
            shoulder_mid = (pos[ls] + pos[rs]) / 2
            hip_mid = (pos[lh] + pos[rh]) / 2
            return float(np.linalg.norm(shoulder_mid - hip_mid))
        return None

    def _compute_head_kinematics(self, pos: dict, dt: float,
                                   torso_length: float | None) -> dict:
        """
        Compute head linear speed and direction-change rate.

        Head position is the centroid of nose + ears.
        Speed is in px/s, optionally normalized by torso length.
        """
        nose = pos.get(self.JOINTS['nose'])
        l_ear = pos.get(self.JOINTS['left_ear'])
        r_ear = pos.get(self.JOINTS['right_ear'])

        # Compute head center from available landmarks
        head_points = [p for p in [nose, l_ear, r_ear] if p is not None]
        if not head_points:
            return {'head_speed': 0, 'head_speed_normalized': 0,
                    'direction_change_rate': 0, 'head_speed_baseline_ratio': 0}

        head_pos = np.mean(head_points, axis=0)

        # Speed calculation
        head_speed = 0.0
        direction_change = 0.0

        if self._prev_head_pos is not None and dt > 0:
            displacement = head_pos - self._prev_head_pos
            head_speed = float(np.linalg.norm(displacement) / dt)

            # Direction change rate (angular velocity of head trajectory)
            if np.linalg.norm(displacement) > 1e-3:
                angle = np.arctan2(displacement[1], displacement[0])
                if hasattr(self, '_prev_head_angle'):
                    d_angle = abs(angle - self._prev_head_angle)
                    if d_angle > np.pi:
                        d_angle = 2 * np.pi - d_angle
                    direction_change = float(d_angle / dt) if dt > 0 else 0
                self._prev_head_angle = angle

        self._prev_head_pos = head_pos.copy()

        # Smoothing
        self._head_speed_history.append(head_speed)
        smoothed_speed = float(np.mean(self._head_speed_history))

        # Normalize by torso length (scale-invariant)
        normalized_speed = smoothed_speed
        if self.normalize_by_torso and torso_length and torso_length > 10:
            normalized_speed = smoothed_speed / torso_length

        # Update baseline
        self._head_speed_baseline.append(normalized_speed)
        baseline = self.get_head_speed_baseline()
        baseline_ratio = normalized_speed / baseline if baseline > 0.01 else 0

        return {
            'head_speed': round(smoothed_speed, 2),
            'head_speed_normalized': round(normalized_speed, 3),
            'direction_change_rate': round(direction_change, 2),
            'head_speed_baseline_ratio': round(baseline_ratio, 2)
        }

    def _empty_metrics(self) -> dict:
        return {
            'joint_angles': {
                'left_elbow': None, 'right_elbow': None,
                'left_knee': None, 'right_knee': None,
                'torso_lean': None
            },
            'head_kinematics': {
                'head_speed': 0, 'head_speed_normalized': 0,
                'direction_change_rate': 0, 'head_speed_baseline_ratio': 0
            },
            'torso_length': None,
            'timestamp': 0
        }
