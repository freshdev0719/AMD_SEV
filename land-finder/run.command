#!/bin/bash
# Finder에서 더블클릭하면 실행됩니다. 처음 한 번은 필요한 패키지를 설치합니다.
# 가짜 데이터로 화면만 보려면 터미널에서: ./run.command --demo
set -e
cd "$(dirname "$0")"

PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3이 필요합니다. 터미널에서 'xcode-select --install'을 실행한 뒤 다시 열어 주세요."
  read -r -n1 -p "아무 키나 누르면 닫힙니다."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "처음 실행합니다. 필요한 패키지를 설치합니다 (1~2분)…"
  "$PY" -m venv .venv
  .venv/bin/python -m pip install -q --upgrade pip
fi
if [ ! -f .venv/.installed ] || [ requirements.txt -nt .venv/.installed ]; then
  .venv/bin/python -m pip install -q -r requirements.txt
  touch .venv/.installed
fi

exec .venv/bin/python -m landfinder "$@"
