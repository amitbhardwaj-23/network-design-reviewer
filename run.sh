#!/usr/bin/env bash
# Run the Network Design Reviewer
# Usage: ./run.sh          — starts the Streamlit UI
#        ./run.sh cli      — CLI mode: ./run.sh cli sample_designs/campus_hld_sample.md
#        ./run.sh seed     — seed the knowledge base from ./knowledge_base/
#        ./run.sh status   — check KB status

set -euo pipefail
cd "$(dirname "$0")"
source venv/bin/activate

# Ensure Ollama is running
if ! pgrep -x "ollama" &>/dev/null; then
  echo "Starting Ollama..."
  ollama serve &>/tmp/ollama.log &
  sleep 3
fi

case "${1:-ui}" in
  seed)   python retriever.py seed ;;
  status) python retriever.py status ;;
  cli)    python agent.py "${2:-sample_designs/campus_hld_sample.md}" ;;
  ui|*)
    echo "Starting Network Design Reviewer UI..."
    echo "Opening: http://localhost:8501"
    streamlit run app.py --server.port 8501 --server.headless false
    ;;
esac
