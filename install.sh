#!/bin/bash
# Neura AI Installer for Mac/Linux

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "============================================================"
echo "   Neura AI - Installer (Mac/Linux)"
echo "============================================================"
echo ""

cd "$SCRIPT_DIR"

# Check Python
echo "[1/6] Checking Python..."
if ! command -v python3 &> /dev/null; then
    echo "  [FAIL] Python 3 not found. Install from python.org"
    exit 1
fi
echo "  [OK] $(python3 --version)"

# Install packages
echo ""
echo "[2/6] Installing Python packages..."
python3 -m pip install --quiet --upgrade textual httpx reportlab pypdf pyperclip
echo "  [OK] Packages installed"

# Check Ollama
echo ""
echo "[3/6] Checking Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "  [INFO] Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
fi
echo "  [OK] Ollama available"

# Start Ollama
echo ""
echo "[4/6] Starting Ollama..."
if ! curl -s http://localhost:11434/api/tags > /dev/null; then
    ollama serve &
    sleep 3
fi
echo "  [OK] Ollama running"

# Pull model and create neura
echo ""
echo "[5/6] Setting up Neura model..."
ollama pull qwen2.5:0.5b
ollama create neura -f "$SCRIPT_DIR/Neura.Modelfile"
echo "  [OK] Neura model created"

# Install command
echo ""
echo "[6/6] Installing 'neura' command..."
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"

cat > "$BIN_DIR/neura" << EOF
#!/bin/bash
python3 "$SCRIPT_DIR/ollama_code.py" "\$@"
EOF
chmod +x "$BIN_DIR/neura"

# Add to PATH if needed
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    SHELL_RC=""
    [[ -f "$HOME/.bashrc" ]] && SHELL_RC="$HOME/.bashrc"
    [[ -f "$HOME/.zshrc" ]] && SHELL_RC="$HOME/.zshrc"
    
    if [[ -n "$SHELL_RC" ]]; then
        echo "export PATH=\"\$PATH:$BIN_DIR\"" >> "$SHELL_RC"
        echo "  [OK] Added to PATH in $SHELL_RC"
    fi
fi

echo ""
echo "============================================================"
echo "   INSTALLATION COMPLETE!"
echo "============================================================"
echo ""
echo "Open a new terminal and type:  neura"
echo ""