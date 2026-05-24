#!/bin/sh
# Wrapper used by launchd / cron to invoke the daily capture & solve.
# Edit PYTHON below if your `python3` isn't the one with playwright
# installed.
set -e
cd "$(dirname "$0")/.."

PYTHON="${PYIPS:-python3}"

"$PYTHON" tools/daily_capture_and_solve.py --headless
