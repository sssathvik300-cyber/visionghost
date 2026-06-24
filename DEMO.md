# FenceGuard Lite Demo Script

This script is designed for a 30-second screen recording to showcase the FenceGuard Lite platform to a TBI researcher.

## Setup
1. Run `docker compose up --build`.
2. Open `http://127.0.0.1:8080`.
3. Have a sample fencing video ready on your desktop (e.g., `fencing_sample.mp4`).

## Recording Script

**0:00 - 0:05 | Connection & Upload**
- Start recording.
- Paste the API key: `fenceguard-secure-demo-key-2026` and click **Connect**.
- Click **Upload Video**, drag in the sample video, and let it process.

**0:05 - 0:15 | Autonomous PTZ & Biomechanics**
- Point to the main video canvas showing the autonomous PTZ framing the target smoothly.
- Briefly gesture towards the **Inset View** in the bottom left, showing the raw frame and the crop box tracking the fencer.
- Move the cursor to the **Biomechanics Panel** to show real-time joint angles updating cleanly.

**0:15 - 0:20 | Event Timeline & Head Speed**
- Direct attention to the **Head Speed (normalized)** chart as a lunge occurs. 
- Highlight the **Event Timeline** as a yellow `LUNGE` event populates.

**0:20 - 0:30 | The Flagship: Head Impact Risk**
- As an impact occurs in the video followed by a Fencing Response, watch the timeline.
- The red **HEAD IMPACT RISK DETECTED** alert card will pulse on screen.
- Hover over the clinical readouts on the card (Head Speed ratio, Direction Change Rate).
- Briefly point to the disclaimer at the bottom of the card and the Methods footer, demonstrating scientific honesty.
- Stop recording.
