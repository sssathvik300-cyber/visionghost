"""
Virtual PTZ (Pan-Tilt-Zoom) camera controller.

Simulates an autonomous camera that smoothly follows the tracked fencer.
Uses exponential moving average (EMA) smoothing on crop center and zoom
to produce a cinematic, jitter-free "broadcast" view.

This is the "PTZ proof" — the closed-loop controller that demonstrates
autonomous camera framing capability.
"""

import numpy as np
import cv2
import logging

logger = logging.getLogger(__name__)


class PTZController:
    """
    Virtual PTZ controller with EMA smoothing.

    Takes the target's position and produces:
    1. A smoothly-panning crop window (the "broadcast" view)
    2. The full frame with the crop rectangle drawn (the "inset" view)
    """

    def __init__(self, config: dict):
        ptz_cfg = config.get('ptz', {})
        self.alpha = ptz_cfg.get('smoothing_alpha', 0.15)
        self.margin = ptz_cfg.get('crop_margin', 1.5)
        self.aspect_w, self.aspect_h = ptz_cfg.get('aspect_ratio', [16, 9])
        self.min_zoom = ptz_cfg.get('min_zoom', 1.0)
        self.max_zoom = ptz_cfg.get('max_zoom', 4.0)

        # Smoothed state
        self._smooth_cx = None
        self._smooth_cy = None
        self._smooth_w = None
        self._smooth_h = None

        # Output resolution for broadcast view
        self.output_w = 960
        self.output_h = 540

    def update(self, frame: np.ndarray,
               bbox: list[float] | None,
               landmarks: list | None = None) -> dict:
        """
        Compute the PTZ crop for this frame.

        Args:
            frame: Full frame (BGR)
            bbox: Target bounding box [x1, y1, x2, y2]
            landmarks: Optional pose landmarks for hip-based centering

        Returns:
            dict with 'ptz_frame', 'inset_frame', 'crop_rect', 'zoom_level'
        """
        fh, fw = frame.shape[:2]

        if bbox is None:
            # No target — return full frame
            return {
                'ptz_frame': cv2.resize(frame, (self.output_w, self.output_h)),
                'inset_frame': frame.copy(),
                'crop_rect': [0, 0, fw, fh],
                'zoom_level': 1.0
            }

        # 1. Compute target center
        # Prefer hip midpoint (more stable than bbox center)
        target_cx, target_cy = self._get_target_center(bbox, landmarks)

        # 2. Compute target crop size from bbox
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        target_w = bw * self.margin
        target_h = bh * self.margin

        # Enforce aspect ratio
        target_w, target_h = self._enforce_aspect_ratio(target_w, target_h)

        # 3. Apply EMA smoothing
        if self._smooth_cx is None:
            self._smooth_cx = target_cx
            self._smooth_cy = target_cy
            self._smooth_w = target_w
            self._smooth_h = target_h
        else:
            self._smooth_cx = self.alpha * target_cx + (1 - self.alpha) * self._smooth_cx
            self._smooth_cy = self.alpha * target_cy + (1 - self.alpha) * self._smooth_cy
            self._smooth_w = self.alpha * target_w + (1 - self.alpha) * self._smooth_w
            self._smooth_h = self.alpha * target_h + (1 - self.alpha) * self._smooth_h

        # 4. Clamp to frame boundaries
        crop_w = max(min(self._smooth_w, fw), fw / self.max_zoom)
        crop_h = max(min(self._smooth_h, fh), fh / self.max_zoom)

        cx = np.clip(self._smooth_cx, crop_w / 2, fw - crop_w / 2)
        cy = np.clip(self._smooth_cy, crop_h / 2, fh - crop_h / 2)

        x1 = int(cx - crop_w / 2)
        y1 = int(cy - crop_h / 2)
        x2 = int(cx + crop_w / 2)
        y2 = int(cy + crop_h / 2)

        # Ensure within bounds
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(fw, x2)
        y2 = min(fh, y2)

        # 5. Crop and resize for broadcast view
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            ptz_frame = cv2.resize(frame, (self.output_w, self.output_h))
        else:
            ptz_frame = cv2.resize(crop, (self.output_w, self.output_h),
                                    interpolation=cv2.INTER_LINEAR)

        # 6. Draw crop rectangle on inset
        inset = frame.copy()
        cv2.rectangle(inset, (x1, y1), (x2, y2), (0, 200, 255), 2, cv2.LINE_AA)
        # Draw crosshair at crop center
        cross_size = 10
        cv2.line(inset, (int(cx) - cross_size, int(cy)),
                 (int(cx) + cross_size, int(cy)), (0, 200, 255), 1, cv2.LINE_AA)
        cv2.line(inset, (int(cx), int(cy) - cross_size),
                 (int(cx), int(cy) + cross_size), (0, 200, 255), 1, cv2.LINE_AA)

        # 7. Compute zoom level
        zoom = fw / crop_w if crop_w > 0 else 1.0
        zoom = np.clip(zoom, self.min_zoom, self.max_zoom)

        return {
            'ptz_frame': ptz_frame,
            'inset_frame': inset,
            'crop_rect': [x1, y1, x2, y2],
            'zoom_level': round(float(zoom), 2)
        }

    def _get_target_center(self, bbox: list[float],
                            landmarks: list | None) -> tuple[float, float]:
        """
        Get the target center. Prefer hip midpoint for stability,
        fall back to bbox center.
        """
        if landmarks:
            # Try to use hip landmarks (23=left_hip, 24=right_hip)
            left_hip = None
            right_hip = None
            for lm in landmarks:
                if lm.id == 23 and lm.visibility > 0.5:
                    left_hip = lm
                elif lm.id == 24 and lm.visibility > 0.5:
                    right_hip = lm

            if left_hip and right_hip:
                return (
                    (left_hip.x + right_hip.x) / 2,
                    (left_hip.y + right_hip.y) / 2
                )

        # Fallback: bbox center
        return (
            (bbox[0] + bbox[2]) / 2,
            (bbox[1] + bbox[3]) / 2
        )

    def _enforce_aspect_ratio(self, w: float, h: float) -> tuple[float, float]:
        """Enforce the configured aspect ratio (default 16:9)."""
        target_ratio = self.aspect_w / self.aspect_h
        current_ratio = w / h if h > 0 else target_ratio

        if current_ratio > target_ratio:
            # Too wide — increase height
            h = w / target_ratio
        else:
            # Too tall — increase width
            w = h * target_ratio

        return w, h

    def reset(self):
        """Reset smoothing state (e.g., when switching targets)."""
        self._smooth_cx = None
        self._smooth_cy = None
        self._smooth_w = None
        self._smooth_h = None
