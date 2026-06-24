# Methods & Limitations

FenceGuard Lite is designed as a screening and exposure-monitoring prototype. It utilizes video-based motion proxies to track kinematics and detect events. 

## Clinical Validation Gap

> [!WARNING]
> **Video-based motion proxies are NOT equivalent to validated clinical concussion assessment tools.** 

FenceGuard Lite uses consumer video at standard frame rates (30–60 fps). This technology has inherent physical limitations when compared to clinical diagnostic instruments:

1. **Undersampling of Impact Pulses**: A true head impact pulse often occurs within 10–15 milliseconds (~1–10 kHz). A 30 fps camera (which captures a frame every 33 ms) undersamples this event by orders of magnitude. It is physically impossible to measure true peak head acceleration (linear or rotational) from standard video.
2. **Head Injury Criterion (HIC) & Brain Injury Criterion (BrIC)**: These diagnostic metrics require precise, high-frequency acceleration data that can only be captured by instrumented sensors (such as the Stanford FITGuard or Prevent Biometrics mouthguards), not by optical motion tracking alone.
3. **Clinical Assessments**: For concussion diagnosis, validated clinical tools such as SCAT5, the King-Devick test, and clinical evaluations by a medical professional remain the gold standard.

## The Fencing Response Detector

The "Fencing Response" is a post-concussive tonic arm posture (one arm flexed, the other extended) named after the en-garde fencing stance (Hosseini & Lifshitz, 2009). 

The Fencing Response detector in this application is an **unvalidated heuristic prototype**. It uses computer vision to detect asymmetric arm extension following a sudden head acceleration event. 

### Future Validation (Phase 2)
For this system to transition from a conceptual prototype to a scientifically validated tool, Phase 2 research must include:
- Time-synchronized comparison against an instrumented mouthguard or IMU sensor.
- Clinical trials correlating video-detected kinematic events with validated biomechanical data.
