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
from flask import Flask, Response
import platform
import os

app = Flask(__name__)

# CAMERA SETUP
def init_camera():
    system  = platform.system()
    machine = platform.machine()
    is_rpi  = (system == "Linux" and ("arm" in machine.lower() or "aarch64" in machine.lower()))

    if is_rpi:
        result = os.system("rpicam-still --list-cameras > /dev/null 2>&1")
        if result != 0:
            raise IOError("No camera detected. Check your connection and try again.")
        print("[camera] Raspberry Pi detected — using rpicam-still")
        return ("rpicam", None)

    # macOS / local machine fallback
    print("[camera] Using OpenCV webcam capture")
    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        raise RuntimeError(
            "Could not open camera. Check that a webcam is connected and "
            "that camera permissions are granted to your terminal / IDE."
        )
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return ("opencv", cam)


CAMERA_TYPE, CAMERA = init_camera()

# FRAME GENERATOR
def generate_frames():
    tmp_path = "/tmp/stream_frame.jpg"
    while True:
        if CAMERA_TYPE == "rpicam":
            ret = os.system(f"rpicam-still -o {tmp_path} --nopreview -t 500 > /dev/null 2>&1")
            if ret != 0 or not os.path.exists(tmp_path):
                print("[camera] rpicam-still failed to capture frame — retrying...")
                continue
            frame_bgr = cv2.imread(tmp_path)
            if frame_bgr is None:
                continue
        else:
            success, frame_bgr = CAMERA.read()
            if not success:
                print("[camera] Failed to read frame — retrying...")
                continue

        _, buffer = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" +
            buffer.tobytes() +
            b"\r\n"
        )

# ROUTES
@app.route("/stream")
def stream():
    """MJPEG stream endpoint — point Streamlit or a browser at this URL."""
    return Response(
        generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

@app.route("/health")
def health():
    """Quick sanity check — useful for confirming the server is up."""
    return {"status": "ok", "camera": CAMERA_TYPE}

# ENTRYPOINT
if __name__ == "__main__":
    port = int(os.getenv("STREAM_PORT", 8080))
    print(f"[camera] Stream running at http://localhost:{port}/stream")
    app.run(host="0.0.0.0", port=port, threaded=True)