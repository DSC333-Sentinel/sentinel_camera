"""
SmartSentinel – Camera Stream
==============================
Streams MJPEG video over HTTP so the Streamlit dashboard can display it.

On MacBook:     uses OpenCV (cv2) to access the built-in webcam.
On Raspberry Pi: attempts to use picamera2 first, falls back to OpenCV
                 if picamera2 is not available.

Requirements:
    pip install flask opencv-python

    # RPI only (if using the Pi camera module):
    pip install picamera2

Run with:
    python camera_stream.py

Stream will be available at:
    http://localhost:8080/stream
"""

import cv2
import time
from flask import Flask, Response
 
app = Flask(__name__)
 
 
# ─────────────────────────────────────────────
# CAMERA ABSTRACTION
# ─────────────────────────────────────────────
 
class PiCamera:
    """Wraps picamera2 for use on Raspberry Pi."""
 
    def __init__(self):
        from picamera2 import Picamera2
        self.cam = Picamera2()
        config = self.cam.create_video_configuration(
            main={"size": (640, 480), "format": "RGB888"},
            controls={"FrameRate": 30}
        )
        self.cam.configure(config)
        self.cam.start()
        # Give the sensor a moment to warm up
        time.sleep(1)
 
    def read_frame(self):
        """Returns a JPEG-encoded frame as bytes, or None on failure."""
        try:
            frame = self.cam.capture_array()
            # picamera2 returns RGB — convert to BGR for OpenCV
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            success, buffer = cv2.imencode(".jpg", frame_bgr)
            return buffer.tobytes() if success else None
        except Exception as e:
            print(f"[PiCamera] Frame error: {e}")
            return None
 
    def release(self):
        self.cam.stop()
 
 
class OpenCVCamera:
    """
    Wraps cv2.VideoCapture.
    Works on Mac (built-in camera), Linux (USB cam), and as a
    fallback on RPI if picamera2 is unavailable.
    """
 
    def __init__(self, index=0):
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
 
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open camera at index {index}. "
                               "Try a different index (0, 1, 2...).")
 
    def read_frame(self):
        """Returns a JPEG-encoded frame as bytes, or None on failure."""
        ret, frame = self.cap.read()
        if not ret:
            return None
        success, buffer = cv2.imencode(".jpg", frame)
        return buffer.tobytes() if success else None
 
    def release(self):
        self.cap.release()
 
 
# ─────────────────────────────────────────────
# CAMERA INIT — try picamera2 first, fall back to OpenCV
# ─────────────────────────────────────────────
 
def init_camera():
    """
    Attempts to initialise picamera2 (RPI).
    Falls back to OpenCV if picamera2 is not installed or fails.
    """
    try:
        cam = PiCamera()
        print("[camera] Using picamera2 (Raspberry Pi)")
        return cam
    except ImportError:
        print("[camera] picamera2 not found — falling back to OpenCV")
    except Exception as e:
        print(f"[camera] picamera2 failed ({e}) — falling back to OpenCV")
 
    try:
        cam = OpenCVCamera(index=0)
        print("[camera] Using OpenCV camera (index 0)")
        return cam
    except RuntimeError as e:
        print(f"[camera] OpenCV index 0 failed ({e}), trying index 1...")
 
    # Last resort — try index 1 (some Macs or USB cameras land here)
    try:
        cam = OpenCVCamera(index=1)
        print("[camera] Using OpenCV camera (index 1)")
        return cam
    except RuntimeError as e:
        raise RuntimeError(
            "No camera could be opened. "
            "Check that your camera is connected and not in use by another app."
        ) from e
 
 
camera = init_camera()
 
 
# ─────────────────────────────────────────────
# MJPEG STREAM GENERATOR
# ─────────────────────────────────────────────
 
def generate_frames():
    """
    Yields a continuous MJPEG byte stream for the /stream endpoint.
    Retries on dropped frames with a short back-off.
    """
    consecutive_failures = 0
    MAX_FAILURES = 10
 
    while True:
        frame_bytes = camera.read_frame()
 
        if frame_bytes is None:
            consecutive_failures += 1
            print(f"[stream] Failed to read frame ({consecutive_failures}/{MAX_FAILURES})")
            if consecutive_failures >= MAX_FAILURES:
                print("[stream] Too many consecutive failures — stopping stream.")
                break
            time.sleep(0.1)
            continue
 
        consecutive_failures = 0
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" +
            frame_bytes +
            b"\r\n"
        )
 
 
# ─────────────────────────────────────────────
# FLASK ROUTES
# ─────────────────────────────────────────────
 
@app.route("/stream")
def stream():
    """MJPEG stream endpoint consumed by the Streamlit dashboard."""
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )
 
@app.route("/health")
def health():
    """Simple health check so the dashboard can verify the stream is up."""
    return {"status": "ok", "camera": camera.__class__.__name__}
 
 
# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
 
if __name__ == "__main__":
    print("[SmartSentinel] Camera stream starting on http://0.0.0.0:8080")
    print("[SmartSentinel] Stream URL: http://localhost:8080/stream")
    try:
        app.run(host="0.0.0.0", port=8080, threaded=True)
    finally:
        print("[SmartSentinel] Releasing camera...")
        camera.release()
 