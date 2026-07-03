#!/usr/bin/env bash
# Starts the VUCA newsletter backend.
# Usage: ./start_newsletter.sh
set -e

cd "$(dirname "$0")"

if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

if [ -z "$GROQ_API_KEY" ]; then
  echo "WARNING: GROQ_API_KEY is not set. /health will report api_key_set=false"
  echo "and /generate will fail. Get a free key at https://console.groq.com/keys"
  echo "and set it in .env or export it before running."
fi

if [ ! -d venv ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -q -r requirements.txt

python app.py
