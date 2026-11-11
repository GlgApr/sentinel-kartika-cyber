#!/usr/bin/env bash
# Setup + jalankan SENTINEL dalam satu perintah:  ./run.sh
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
.venv/bin/python src/data_ingestion.py
.venv/bin/python src/detection_engine.py
exec .venv/bin/streamlit run app/dashboard.py
