#!/bin/bash
# Start Der KI-osk on the local network (web player + RSS feed + audio).
# Port and address are set in config/default_config.yaml (server.port, server.public_ip).
# Press Ctrl+C to stop.

cd "$(dirname "$0")"

if [ -f venv/bin/activate ]; then
    source venv/bin/activate
fi

python src/main.py --server
