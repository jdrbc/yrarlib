#!/bin/bash

# Library App Runner Script
# Simple script to run the library server for local development

set -e

# Change to app directory
cd "$(dirname "$0")/app"

# Check if .env exists
if [ ! -f "../.env" ]; then
    echo "⚠️  Warning: .env file not found in project root"
    echo "   Anna's Archive integration may not work without API credentials"
    echo ""
fi

# Display startup message
echo "📚 Starting Library Server..."
echo ""
echo "Library path: $(pwd)/../test_library"
echo "Server will be available at: http://localhost:26657"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Run the server using uv
uv run python -m server
