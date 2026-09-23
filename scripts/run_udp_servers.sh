#!/usr/bin/env bash
set -Eeuo pipefail
shopt -s nullglob

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

pids=()

cleanup() {
  trap - EXIT INT TERM
  echo "Stopping terminal windows..."

  ((${#pids[@]})) || exit 0

  kill -TERM "${pids[@]}" 2>/dev/null || true

  local deadline=$((SECONDS + 5))
  for pid in "${pids[@]}"; do
    while kill -0 "$pid" 2>/dev/null; do
      if (( SECONDS >= deadline )); then
        kill -KILL "$pid" 2>/dev/null || true
        break
      fi
      sleep 0.2
    done
    wait "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

for udp in src/udp/*_udp_server.py; do
  echo "Starting $udp ..."
  base="$(basename "$udp" .py)"
  abs_udp="$project_root/$udp"

  if [[ "$base.py" == "spectrometer_udp_server.py" ]]; then
    lxterminal --title="$base" -e bash -lc \
      "cd '$project_root'; echo 'Starting $base (sudo)...'; sudo python3 '$abs_udp'; echo; echo 'Process ended. Press Enter to close.'; read -r" &
  else
    lxterminal --title="$base" -e bash -lc \
      "cd '$project_root'; echo 'Starting $base...'; python3 '$abs_udp'; echo; echo 'Process ended. Press Enter to close.'; read -r" &
  fi

  pids+=("$!")
done

if ((${#pids[@]} == 0)); then
  echo "No *_udp_server.py scripts found under src/udp/"
fi

wait