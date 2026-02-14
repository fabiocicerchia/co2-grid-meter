#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
fi

source .venv/bin/activate
python3 -m web.server &
python3 -m mock.mock_pico
