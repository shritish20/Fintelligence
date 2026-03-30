#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# sync_shared.sh — Sync shared utilities to all backend containers
# Run after editing anything in shared/
# ─────────────────────────────────────────────────────────────────────────────
set -e

SHARED_DIR="$(dirname "$0")/shared"
BACKENDS=("backend/volguard" "backend/mf" "backend/equity" "backend/tax")
FILES=("auth_utils.py" "db_utils.py" "subscription_gate.py")

for FILE in "${FILES[@]}"; do
  SRC="$SHARED_DIR/$FILE"
  if [ ! -f "$SRC" ]; then
    echo "⚠️  Skipping $FILE — not found in shared/"
    continue
  fi
  for BACKEND in "${BACKENDS[@]}"; do
    DEST="$BACKEND/$FILE"
    cp "$SRC" "$DEST"
    echo "✅  $SRC → $DEST"
  done
done

echo ""
echo "Done. Commit all changes together."
