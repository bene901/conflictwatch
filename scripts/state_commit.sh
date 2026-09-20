#!/usr/bin/env bash
# Committet state/ und pusht OHNE --force. Hat ein anderer Lauf den Branch inzwischen verändert,
# lehnt Git den Push ab -> Exit 1 -> der Workflow bricht vor dem Deploy ab.
# Gibt den SHA des aktuellen State-Commits auf stdout aus (letzte Zeile).
set -euo pipefail
dir="$1"; msg="$2"
git -C "$dir" add state
if git -C "$dir" diff --cached --quiet; then
  echo "Keine Änderung am Bestand." >&2
else
  git -C "$dir" commit --quiet -m "$msg"
  if ! git -C "$dir" push --quiet origin HEAD:data-state 2>&1 >&2; then
    echo "PUSH ABGELEHNT: data-state wurde inzwischen verändert. Abbruch vor dem Deploy." >&2
    exit 1
  fi
fi
if git -C "$dir" rev-parse --verify -q HEAD >/dev/null; then
  git -C "$dir" rev-parse HEAD
else
  echo "0000000"
fi
