#!/usr/bin/env bash
set -euo pipefail

# Flora install script
# Usage: bash install.sh [config_path]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_PATH="${1:-flora.toml}"

echo "Flora — Autonomous Herb Garden Agent"
echo "======================================"

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_min="3.12"
if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" 2>/dev/null; then
    echo "ERROR: Python 3.12+ required (found $python_version)"
    exit 1
fi
echo "Python $python_version — OK"

# Install package with pip
echo "Installing Flora dependencies..."
pip3 install -e "$SCRIPT_DIR"[dev] --quiet

# Set up config if not present
if [ ! -f "$CONFIG_PATH" ]; then
    echo ""
    echo "No config found. Copying example config to $CONFIG_PATH"
    cp "$SCRIPT_DIR/flora.example.toml" "$CONFIG_PATH"
    echo "IMPORTANT: Edit $CONFIG_PATH with your sensor MAC addresses, GPIO pins, and API keys."
fi

# Install systemd service (Linux only)
if command -v systemctl &>/dev/null && [ -f "$SCRIPT_DIR/flora.service" ]; then
    echo ""
    echo "Installing systemd service..."
    # Replace placeholder paths in service file
    service_content=$(sed \
        "s|/home/pi/flora-app|$SCRIPT_DIR|g" \
        "$SCRIPT_DIR/flora.service")
    sudo tee /etc/systemd/system/flora.service > /dev/null <<< "$service_content"
    sudo systemctl daemon-reload
    sudo systemctl enable flora.service
    echo "Systemd service installed and enabled."
    echo "Start with: sudo systemctl start flora"
else
    echo "Note: systemd not available — run Flora manually with: flora $CONFIG_PATH"
fi

echo ""
echo "Installation complete!"
echo "Edit $CONFIG_PATH, then run: flora $CONFIG_PATH"
echo "Dashboard will be available at: http://localhost:8000"
