#!/bin/bash
set -e # Interrompe lo script in caso di errori

WORKSPACE_DIR="${1:-$(pwd)}"

echo "Environment configuration..."
mkdir -p /config/custom_components
ln -sf "$WORKSPACE_DIR/custom_components/x728" /config/custom_components/x728
cp "$WORKSPACE_DIR/.devcontainer/start.sh" /start.sh
