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
import subprocess

app = Flask(__name__)

# CAMERA SETUP
def init_camera():
    system  = platform.system()
    machine = platform.machine()
    is_rpi  = (system == "Linux" and ("arm" in machine.lower() or "aarch64" in machine.lower()))

    if is_rpi:
        import subprocess
        proc = subprocess.Popen(
            [
                "rpicam-vid",
                "-t",          "0",         # run indefinitely
                "--codec",     "mjpeg",      # output MJPEG not h264
                "--width",     "640",
                "--height",    "480",
                "--framerate", "15",         # bump to 30 if your Pi can handle it
                "--nopreview",
                "-o",          "-",          # pipe to stdout
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        print("[camera] Raspberry Pi detected — using rpicam-vid (MJPEG pipe)")
        return ("rpicam-vid", proc)

    # macOS / local fallback
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
    if CAMERA_TYPE == "rpicam-vid":
        # Read the raw MJPEG byte stream from rpicam-vid stdout.
        # JPEG frames are delimited by SOI (0xFF 0xD8) and EOI (0xFF 0xD9) markers.
        buf = b""
        while True:
            chunk = CAMERA.stdout.read(4096)
            if not chunk:
                break
            buf += chunk

            start = buf.find(b"\xff\xd8")  # JPEG SOI marker
            end   = buf.find(b"\xff\xd9")  # JPEG EOI marker

            if start != -1 and end != -1 and end > start:
                jpg = buf[start:end + 2]
                buf = buf[end + 2:]         # keep remainder for next frame

                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" +
                    jpg +
                    b"\r\n"
                )
    else:
        while True:
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