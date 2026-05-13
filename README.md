# Sentinel Camera
**DSC 333 · Spring 2026 · Jose and Aylin**

MJPEG camera stream server for the Sentinel security system. Runs on any device with a camera. Compatible with a Raspberry Pi with an ArduCam or a computer with a built-in webcam. It streams video over HTTP so the Sentinel app can communicate with it.

---

## How It Works

`sentinel_camera.py` detects the platform it is running on and selects the appropriate camera backend automatically:

- **Raspberry Pi (ARM/AArch64):** uses `rpicam-vid` to stream from the Pi camera module at full sensor resolution via an MJPEG pipe
- **Any Webcam Camera** uses OpenCV to access the built-in or connected webcam

A background thread continuously reads frames into a shared buffer. Multiple clients (the Sentinel dashboard, the detection pipeline) can connect to the stream simultaneously without interfering with each other.

---

## Requirements

- Python 3.10+
- A connected camera (Pi camera module or webcam)
- On Raspberry Pi: `rpicam-apps` installed

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/DSC333-Sentinel/sentinel_camera.git
cd sentinel-camera
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Your `.env` only needs one variable:

```dotenv
STREAM_PORT=8080
```

Change the port if 8080 is already in use on your device.

### 3. Raspberry Pi only — install rpicam-apps

```bash
sudo apt install -y rpicam-apps
```

Verify your camera is detected:
```bash
rpicam-still --list-cameras
```

You should see your camera listed (e.g. `IMX219`). If nothing appears, check the ribbon cable connection.

### 4. Start

Run the start script

```bash
chmod +x start.sh
./start.sh
```

The script will:
- Create a Python virtual environment if one doesn't exist
- Install all dependencies from `requirements.txt`
- Check for your `.env` file
- Start the camera stream

You can also use `python3 sentinel_camera.py` but I recommend using the start.sh script to make things easier.

---

## Stream URLs

When the script starts, it prints the URLs to use:

```
┌─────────────────────────────────────────────┐
│           Sentinel Camera Stream            │
├─────────────────────────────────────────────┤
│  Local:    http://localhost:8080/stream     │
│  Network:  http://192.168.1.42:8080/stream  │
│                                             │
│  Copy the IP into the Sentinel.             │
│  dashboard under Cameras → Add New Camera   │
└─────────────────────────────────────────────┘
```

Use the **IP Address** when adding the camera in the Sentinel dashboard. Use **localhost** only if the dashboard is running on the same machine.

You can also verify the stream is working by opening the Network URL in any browser — you should see a live video feed.

---

## Adding the Camera to Sentinel

In the Sentinel dashboard:

1. Go to **Cameras**
2. Click **Add New Camera**
3. Enter a name and location
4. Enter the IP address and port of the device running this script
5. Click **➕ Add Camera**

The stream will appear on the **Live Feed** page automatically.

---

## Project Structure

```
sentinel-camera/
├── sentinel_camera.py   # Camera stream server
├── start.sh             # Startup script
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
└── .env                 # Your values (not committed)
```

---

## requirements.txt

```
flask
opencv-python
python-dotenv
```

On Raspberry Pi, `rpicam-apps` is installed via `apt` (see Setup above), not pip.

---

## Camera Settings

The stream resolution and framerate are set in `sentinel_camera.py`. Current defaults for the Raspberry Pi:

- Resolution: `1640 x 1232` (half-resolution mode of the IMX219 — uses full sensor area)
- Framerate: `15 fps`
- ROI: `0,0,1,1` (full sensor, no crop)

To adjust, edit the `rpicam-vid` arguments in `init_camera()`.

For the webcam (macOS/Linux), the default resolution is `640 x 480`. This can be changed by editing the `CAP_PROP_FRAME_WIDTH` and `CAP_PROP_FRAME_HEIGHT` values in the same function.

---

## Stopping

Press `Ctrl+C` in the terminal. The stream will stop cleanly and the virtual environment will be deactivated.
