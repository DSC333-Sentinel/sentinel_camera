"""
Sentinel – Camera Stream
==============================
Detects all connected cameras and streams each one over HTTP as MJPEG.
Each camera gets its own port starting from STREAM_PORT (default 8080).

  Camera 0 → http://<ip>:8080/stream
  Camera 1 → http://<ip>:8081/stream
  ...

On a personal laptop: uses OpenCV to access connected webcams.
On Raspberry Pi:      uses rpicam-vid with --camera <index>.

RPI only — install rpicam-apps first:
    sudo apt install -y rpicam-apps

Run with:
    python3 sentinel_camera.py

Add each camera in the Sentinel dashboard under Cameras → Add New Camera
using the IP and port shown at startup.
"""

import cv2
import os
import platform
import subprocess
import threading
import time
from flask import Flask, Response
from dotenv import load_dotenv

load_dotenv()

BASE_PORT   = int(os.getenv("STREAM_PORT", 8080))
RETRY_DELAY = 3   # seconds between reconnect attempts on disconnect


# PLATFORM DETECTION

def is_raspberry_pi():
    system  = platform.system()
    machine = platform.machine()
    return system == "Linux" and ("arm" in machine.lower() or "aarch64" in machine.lower())


# CAMERA ENUMERATION

def find_opencv_cameras(max_index=8):
    """
    Tries VideoCapture indices 0 through max_index.
    Returns a list of indices that successfully opened.
    """
    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            found.append(i)
            cap.release()
    return found

def find_rpi_cameras():
    """
    Asks rpicam-still how many cameras are attached.
    Returns a list of indices. Falls back to [0] if detection fails.
    """
    try:
        result = subprocess.run(
            ["rpicam-still", "--list-cameras"],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout + result.stderr
        indices = [
            int(line.split(":")[0].strip())
            for line in output.splitlines()
            if line.strip() and line.strip()[0].isdigit() and ":" in line
        ]
        return indices if indices else [0]
    except Exception:
        return [0]


# CAMERA STREAM CLASS

class CameraStream:
    """
    Manages one camera — capture loop, shared frame buffer,
    Flask app, and server thread. Each instance runs on its own port.
    """

    def __init__(self, index: int, port: int, rpi: bool):
        self.index        = index
        self.port         = port
        self.rpi          = rpi
        self.latest_frame = None
        self.lock         = threading.Lock()
        self.connected    = False
        self.flask_app    = self._build_flask_app()

    def _build_flask_app(self):
        app = Flask(f"sentinel_camera_{self.index}")

        @app.route("/stream")
        def stream():
            return Response(
                self._generate_frames(),
                mimetype="multipart/x-mixed-replace; boundary=frame"
            )

        @app.route("/health")
        def health():
            return {
                "status":   "ok" if self.connected else "disconnected",
                "camera":   "rpicam-vid" if self.rpi else "opencv",
                "index":    self.index,
                "port":     self.port,
            }

        return app

    def _generate_frames(self):
        """Each HTTP client reads from the shared frame buffer independently."""
        while True:
            with self.lock:
                frame = self.latest_frame
            if frame is None:
                time.sleep(0.05)
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" +
                frame +
                b"\r\n"
            )
            time.sleep(0.05)  # ~20fps cap

    def _capture_rpi(self):
        """Capture loop for Raspberry Pi using rpicam-vid."""
        while True:
            print(f"[camera {self.index}] Starting rpicam-vid...")
            try:
                proc = subprocess.Popen(
                    [
                        "rpicam-vid",
                        "-t",          "0",
                        "--camera",    str(self.index),
                        "--codec",     "mjpeg",
                        "--width",     "1640",
                        "--height",    "1232",
                        "--framerate", "15",
                        "--roi",       "0,0,1,1",
                        "--nopreview",
                        "-o",          "-",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                self.connected = True
                buf = b""
                while True:
                    chunk = proc.stdout.read(4096)
                    if not chunk:
                        raise IOError("rpicam-vid process ended unexpectedly.")
                    buf += chunk
                    start = buf.find(b"\xff\xd8")
                    end   = buf.find(b"\xff\xd9")
                    if start != -1 and end != -1 and end > start:
                        jpg = buf[start:end + 2]
                        buf = buf[end + 2:]
                        with self.lock:
                            self.latest_frame = jpg

            except Exception as e:
                self.connected = False
                print(f"[camera {self.index}] Disconnected: {e}. Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)

    def _capture_opencv(self):
        """Capture loop for OpenCV webcams with reconnect handling."""
        cap = None
        while True:
            if cap is None or not cap.isOpened():
                self.connected = False
                print(f"[camera {self.index}] Connecting to OpenCV camera {self.index}...")
                cap = cv2.VideoCapture(self.index)
                if not cap.isOpened():
                    print(f"[camera {self.index}] Could not open. Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.connected = True
                print(f"[camera {self.index}] Connected on port {self.port}.")

            success, frame_bgr = cap.read()
            if not success:
                self.connected = False
                print(f"[camera {self.index}] Frame read failed — disconnected. Retrying in {RETRY_DELAY}s...")
                cap.release()
                cap = None
                time.sleep(RETRY_DELAY)
                continue

            _, buffer = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
            with self.lock:
                self.latest_frame = buffer.tobytes()

    def start(self):
        """Start the capture loop and Flask server in background threads."""
        capture_fn = self._capture_rpi if self.rpi else self._capture_opencv
        threading.Thread(target=capture_fn, daemon=True).start()
        threading.Thread(
            target=lambda: self.flask_app.run(
                host="0.0.0.0",
                port=self.port,
                threaded=True,
                use_reloader=False,
            ),
            daemon=True,
        ).start()


# ENTRYPOINT

if __name__ == "__main__":
    import socket

    rpi = is_raspberry_pi()
    print("")
    print("Sentinel Camera Stream")
    print("======================")
    print(f"Platform: {'Raspberry Pi' if rpi else 'macOS / Linux (OpenCV)'}")
    print("")

    # Enumerate all available cameras
    indices = find_rpi_cameras() if rpi else find_opencv_cameras()
    if not indices:
        print("ERROR: No cameras detected. Check connections and try again.")
        exit(1)

    print(f"Found {len(indices)} camera(s): indices {indices}")
    print("")

    # Resolve local IP
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
    except Exception:
        local_ip = "localhost"

    # Start a stream for each camera
    streams = []
    for idx in indices:
        port   = BASE_PORT + idx
        stream = CameraStream(index=idx, port=port, rpi=rpi)
        stream.start()
        streams.append(stream)

    # Print connection info
    print("┌──────────────────────────────────────────────────────┐")
    print("│  Camera streams running                              │")
    print("├──────────────────────────────────────────────────────┤")
    for s in streams:
        print(f"│  Camera {s.index}  →  IP: {local_ip:<20} Port: {s.port}  │")
    print("├──────────────────────────────────────────────────────┤")
    print("│  Add each camera in Sentinel:                        │")
    print("│  Cameras → Add New Camera → IP and port above        │")
    print("└──────────────────────────────────────────────────────┘")
    print("")
    print("Press Ctrl+C to stop all streams.")
    print("")

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[camera] Stopped by user.")