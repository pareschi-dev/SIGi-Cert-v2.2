#!/usr/bin/env bash
set -e

python -m venv .venv
if [ "$(uname)" = "Darwin" ] || [ "$(uname)" = "Linux" ]; then
  . .venv/bin/activate
else
  . .venv\Scripts\activate
fi

pip install --upgrade pip
pip install -r requirements.txt
pip install -e .

python -m playwright install chromium
