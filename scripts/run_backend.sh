#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -d ".venv" ]; then
  echo "Python venv not found. Run: ./scripts/setup_backend.sh"
  exit 1
fi

source .venv/bin/activate
set -a
source "$ROOT_DIR/.env"
set +a

python3 - <<'PY'
import os
import sys
from sqlalchemy import create_engine, text

database_url = os.getenv("DATABASE_URL", "")
if not database_url:
    print("DATABASE_URL is not set in .env")
    sys.exit(1)

try:
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
except Exception as exc:  # noqa: BLE001
    print("Database preflight failed. Check DATABASE_URL, role, password, and db existence.")
    print(f"Details: {exc}")
    sys.exit(1)
PY

cd "$ROOT_DIR/backend"
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
