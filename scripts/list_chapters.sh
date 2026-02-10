#!/usr/bin/env bash
# List all chapter paths in order (Section1/Chapter_1 ... Section6/Chapter_57).
# Usage: ./scripts/list_chapters.sh
# From repo root: bash scripts/list_chapters.sh

cd "$(dirname "$0")/.." || exit 1
for section in Section1 Section2 Section3 Section4 Section5 Section6; do
  for f in "$section"/Chapter_*.md; do
    [ -f "$f" ] && echo "$f"
  done
done | sort -V
