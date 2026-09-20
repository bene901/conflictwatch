#!/usr/bin/env bash
# Holt den Branch data-state (Tiefe 1) nach $2 oder legt ein leeres Repo für den ersten Lauf an.
# Aufruf: state_checkout.sh <remote-url> <zielordner>
set -euo pipefail
remote="$1"; dir="$2"
if git ls-remote --exit-code --heads "$remote" data-state >/dev/null 2>&1; then
  git clone --quiet --depth 1 --branch data-state --single-branch "$remote" "$dir"
else
  echo "data-state existiert noch nicht – erster Lauf, neuer verwaister Branch."
  mkdir -p "$dir"
  git -C "$dir" init --quiet -b data-state
  git -C "$dir" remote add origin "$remote"
fi
git -C "$dir" config user.name "conflictwatch-bot"
git -C "$dir" config user.email "conflictwatch-bot@users.noreply.github.com"
mkdir -p "$dir/state"
