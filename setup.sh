#!/bin/bash
# Setup script for Der KI-osk

set -e
cd "$(dirname "$0")"

echo "=========================================="
echo "Der KI-osk - Setup"
echo "=========================================="

echo "Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "Installing Python dependencies (this downloads PyTorch and can take a while)..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Checking system dependencies..."
if command -v ollama &> /dev/null; then
    echo "[✓] Ollama is installed"
else
    echo "[✗] Ollama is not installed - install from https://ollama.com/"
fi

mkdir -p data logs output/audio output/chapters

echo ""
echo "=========================================="
echo "Setup completed!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Activate the virtual environment: source venv/bin/activate"
echo "2. Start Ollama:                     ollama serve"
echo "3. Download the LLM:                 ollama pull gpt-oss:20b"
echo "4. Set tts.ref_audio / tts.ref_text and server.public_ip in config/default_config.yaml"
echo "5. Validate the setup:               python src/main.py --validate"
echo "6. Generate an episode:              python src/main.py --fetch --generate"
echo "7. Start the servers:                ./START_SERVER.sh"
