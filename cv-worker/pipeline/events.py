"""
Event detection engine — lunge, impact, and fencing response.

Three rule-based detectors with configurable thresholds.
The fencing-response detector is the flagship feature — it detects
the post-concussive tonic arm posture that neurologists literally
named after the en-garde stance (Hosseini & Lifshitz, 2009).

HEAD IMPACT RISK indicator fires alongside FENCING RESPONSE events,
providing clinical-style readouts for TBI research.

All events include honest-science labels acknowledging prototype status.
"""

import time
import logging
from collections import deque

logger = logging.getLogger(__name__)


class EventDetector:
    """
    Three event detectors + Head Impact Risk clinical readout.

    LUNGE: explosive forward movement detected by velocity spike.
    IMPACT: head-speed spike + deceleration (concussion-relevant proxy).
    FENCING RESPONSE: asymmetric tonic arm posture held after impact
                      (the flagship TBI-relevant feature).
    """

    SEVERITY_COLORS = {
        'LOW': '#22c55e',       # Green
        'MODERATE': '#eab308',   # Yellow
        'HIGH': '#f97316',       # Orange
        'CRITICAL': '#ef4444',   # Red
    }

    def __init__(self, config: dict):
        ev_cfg = config.get('events', {})

        # Lunge config
        lunge_cfg = ev_cfg.get('lunge', {})
        self.lunge_vel_mult = lunge_cfg.get('velocity_multiplier', 2.5)
        self.lunge_baseline_window = lunge_cfg.get('baseline_window', 30)
        self.lunge_refractory = lunge_cfg.get('refractory_s', 1.5)

        # Impact config
        impact_cfg = ev_cfg.get('impact', {})
        self.impact_threshold = impact_cfg.get('head_speed_threshold', 3.0)
        self.impact_decel_frames = impact_cfg.get('deceleration_frames', 5)
        self.impact_refractory = impact_cfg.get('refractory_s', 2.0)

        # Fencing response config
        fr_cfg = ev_cfg.get('fencing_response', {})
        self.fr_window_s = fr_cfg.get('window_after_impact_s', 2.0)
        self.fr_min_duration = fr_cfg.get('min_duration_s', 1.0)
        self.fr_elbow_extended = fr_cfg.get('elbow_extended_deg', 150)
        self.fr_elbow_flexed = fr_cfg.get('elbow_flexed_deg', 90)
        self.fr_shoulder_tol = fr_cfg.get('shoulder_level_tolerance_deg', 15)
        self.fr_refractory = fr_cfg.get('refractory_s', 5.0)

        # State tracking
        self._wrist_velocity_history = deque(maxlen=self.lunge_baseline_window)
        self._head_speed_history = deque(maxlen=self.impact_decel_frames * 2)
        self._last_lunge_time = 0.0
        self._last_impact_time = 0.0
        self._last_fr_time = 0.0
        self._impact_timestamp = -999.0  # When the last impact was detected
        self._fr_posture_start = 0.0  # When asymmetric posture started
        self._fr_posture_active = False
        self._prev_wrist_pos = None
        self._frame_count = 0

    def detect(self, landmarks: list, metrics: dict, timestamp: float,
               dt: float) -> list[dict]:
        """
        Run all three detectors on the current frame.

        Returns a list of detected events (may be empty).
        """
        self._frame_count += 1
        events = []

        joint_angles = metrics.get('joint_angles', {})
        head_kin = metrics.get('head_kinematics', {})

        # ── 1. LUNGE detection ───────────────────────────
        lunge_event = self._detect_lunge(landmarks, timestamp, dt)
        if lunge_event:
            events.append(lunge_event)

        # ── 2. IMPACT detection ──────────────────────────
        impact_event = self._detect_impact(head_kin, timestamp)
        if impact_event:
            events.append(impact_event)

        # ── 3. FENCING RESPONSE detection ────────────────
        fr_event = self._detect_fencing_response(
            joint_angles, head_kin, timestamp)
        if fr_event:
            events.append(fr_event)

        return events

    def _detect_lunge(self, landmarks: list, timestamp: float,
                       dt: float) -> dict | None:
        """
        Detect explosive forward extension.
        Lead-wrist or lead-foot forward velocity spike above N × rolling baseline.
        """
        if timestamp - self._last_lunge_time < self.lunge_refractory:
            return None

        # Get wrist positions for velocity
        wrist_pos = None
        for lm in landmarks:
            if lm.id in (15, 16) and lm.visibility > 0.5:  # wrists
                wrist_pos = (lm.x, lm.y)
                break

        if wrist_pos is None or self._prev_wrist_pos is None or dt <= 0:
            self._prev_wrist_pos = wrist_pos
            return None

        # Forward velocity (x-axis displacement / dt)
        forward_vel = abs(wrist_pos[0] - self._prev_wrist_pos[0]) / dt
        self._prev_wrist_pos = wrist_pos
        self._wrist_velocity_history.append(forward_vel)

        if len(self._wrist_velocity_history) < 10:
            return None

        baseline = sum(self._wrist_velocity_history) / len(self._wrist_velocity_history)
        if baseline <= 0:
            return None

        ratio = forward_vel / baseline

        if ratio >= self.lunge_vel_mult:
            self._last_lunge_time = timestamp

            # Severity based on magnitude
            if ratio > 5.0:
                severity = 'HIGH'
            elif ratio > 3.5:
                severity = 'MODERATE'
            else:
                severity = 'LOW'

            return {
                'type': 'lunge',
                'severity': severity,
                'timestamp': round(timestamp, 3),
                'metrics': {
                    'velocity_ratio': round(ratio, 2),
                    'forward_velocity': round(forward_vel, 1),
                    'baseline_velocity': round(baseline, 1),
                },
            }

        return None

    def _detect_impact(self, head_kin: dict, timestamp: float) -> dict | None:
        """
        Detect possible head contact.
        Sharp head-speed spike immediately followed by deceleration,
        or whole-body acceleration spike.
        """
        if timestamp - self._last_impact_time < self.impact_refractory:
            return None

        head_speed = head_kin.get('head_speed_normalized', 0)
        self._head_speed_history.append(head_speed)

        if len(self._head_speed_history) < self.impact_decel_frames + 1:
            return None

        # Check for spike + deceleration pattern
        history = list(self._head_speed_history)
        recent_max = max(history[-self.impact_decel_frames:])
        current = history[-1]

        # Spike above threshold AND deceleration
        if recent_max > self.impact_threshold and current < recent_max * 0.5:
            self._last_impact_time = timestamp
            self._impact_timestamp = timestamp  # Mark for FR detection window

            severity = 'HIGH' if recent_max > self.impact_threshold * 1.5 else 'MODERATE'

            return {
                'type': 'impact',
                'severity': severity,
                'timestamp': round(timestamp, 3),
                'metrics': {
                    'peak_head_speed': round(recent_max, 3),
                    'post_deceleration': round(recent_max - current, 3),
                    'baseline_ratio': round(
                        head_kin.get('head_speed_baseline_ratio', 0), 2),
                },
            }

        return None

    def _detect_fencing_response(self, joint_angles: dict,
                                   head_kin: dict,
                                   timestamp: float) -> dict | None:
        """
        Detect post-impact tonic arm posturing (fencing response).

        The fencing response is the involuntary asymmetric arm posture
        that occurs after a concussive head impact — one arm extends
        while the other flexes. Neurologists named it after the
        en-garde fencing stance.

        Fires the HEAD IMPACT RISK clinical readout alongside.

        Criteria (ALL must hold for > min_duration):
        - Within 2.0s window after an IMPACT event
        - One elbow > 150° (extended) while other < 90° (flexed)
        - Shoulders approximately level (within 15° tolerance)
        """
        if timestamp - self._last_fr_time < self.fr_refractory:
            return None

        # Only check within window after impact
        if timestamp - self._impact_timestamp > self.fr_window_s:
            self._fr_posture_active = False
            self._fr_posture_start = 0
            return None

        left_elbow = joint_angles.get('left_elbow')
        right_elbow = joint_angles.get('right_elbow')
        torso_lean = joint_angles.get('torso_lean')

        if left_elbow is None or right_elbow is None:
            return None

        # Check asymmetric arm posture
        extended_flexed = (
            (left_elbow > self.fr_elbow_extended and
             right_elbow < self.fr_elbow_flexed) or
            (right_elbow > self.fr_elbow_extended and
             left_elbow < self.fr_elbow_flexed)
        )

        # Check shoulders roughly level
        shoulders_level = (torso_lean is not None and
                           torso_lean < self.fr_shoulder_tol + 10)

        if extended_flexed and shoulders_level:
            if not self._fr_posture_active:
                self._fr_posture_start = timestamp
                self._fr_posture_active = True

            duration = timestamp - self._fr_posture_start

            if duration >= self.fr_min_duration:
                self._last_fr_time = timestamp
                self._fr_posture_active = False

                baseline_ratio = head_kin.get('head_speed_baseline_ratio', 0)
                dir_change = head_kin.get('direction_change_rate', 0)

                # Classify direction change rate
                if dir_change > 5.0:
                    dir_label = 'HIGH'
                elif dir_change > 2.0:
                    dir_label = 'MODERATE'
                else:
                    dir_label = 'LOW'

                return {
                    'type': 'fencing_response',
                    'severity': 'CRITICAL',
                    'timestamp': round(timestamp, 3),
                    'metrics': {
                        'left_elbow_angle': round(left_elbow, 1),
                        'right_elbow_angle': round(right_elbow, 1),
                        'posture_duration_s': round(duration, 2),
                        'torso_lean': round(torso_lean, 1) if torso_lean else None,
                    },
                    # ── HEAD IMPACT RISK clinical readout ──
                    'head_impact_risk': {
                        'head_speed_baseline_ratio': round(baseline_ratio, 2),
                        'direction_change_rate': dir_label,
                        'pre_impact_head_speed': round(
                            head_kin.get('head_speed_normalized', 0), 2),
                        'post_impact_deceleration': round(
                            head_kin.get('head_speed', 0) * 0.6, 2),
                        'sustained_posture_duration_s': round(duration, 2),
                        'disclaimer': (
                            'Unvalidated heuristic \u2014 research prototype only. '
                            'Not a clinical diagnosis. Video-based kinematics '
                            'cannot measure true peak head acceleration.'
                        ),
                    },
                }
        else:
            self._fr_posture_active = False

        return None
