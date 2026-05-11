#!/bin/bash
# Sentinel – Camera Start Script (macOS / Linux / Raspberry Pi)
# Runs sentinel_camera.py only.
# Usage: ./start.sh

VENV_DIR=".venv"
REQUIREMENTS="requirements.txt"

echo ""
echo "Sentinel Camera Startup"
echo "========================="
echo ""

# VIRTUAL ENVIRONMENT
if [ ! -d "$VENV_DIR" ]; then
    echo "[camera] No virtual environment found. Creating one..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "[camera] ERROR: Failed to create virtual environment. Is python3 installed?"
        exit 1
    fi
    echo "[camera] Virtual environment created at $VENV_DIR"

    echo "[camera] Installing requirements..."
    "$VENV_DIR/bin/pip" install --upgrade pip -q
    "$VENV_DIR/bin/pip" install -r "$REQUIREMENTS" -q
    if [ $? -ne 0 ]; then
        echo "[camera] ERROR: Failed to install requirements."
        exit 1
    fi
    echo "[camera] Requirements installed."
else
    echo "[camera] Virtual environment found at $VENV_DIR"
fi

# Activate the virtual environment
source "$VENV_DIR/bin/activate"
echo "[camera] Virtual environment activated."
echo ""

# .ENV CHECK
if [ ! -f ".env" ]; then
    echo ""
    echo "Warning!"
    echo "No .env file found in this directory."
    echo ""
    echo "Create one by running:"
    echo "cp .env.example .env"
    echo "Then fill in your values and re-run this script."
    echo ""
    deactivate 2>/dev/null
    exit 1
fi
echo "[camera] .env file found."
echo ""


# CLEANUP
cleanup() {
    echo ""
    echo "[camera] Shutting down..."

    [ -n "$CAMERA_PID" ] && kill "$CAMERA_PID" 2>/dev/null
    sleep 1
    [ -n "$CAMERA_PID" ] && kill -9 "$CAMERA_PID" 2>/dev/null

    deactivate 2>/dev/null

    echo "[camera] Camera stopped. Goodbye."
    exit 0
}

trap cleanup SIGINT SIGTERM

# START CAMERA
echo "[camera] Starting camera stream..."
python3 sentinel_camera.py &
CAMERA_PID=$!

echo ""
echo Camera stream running.
echo ""

wait $CAMERA_PID
cleanup