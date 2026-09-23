#!/usr/bin/env bash
# enable strict error handling. -E ERR traps are inherited by functions, -e exit if any command fails, -u unset variable is error, -o pipefail pipe fails if command fails. This prevents silent errors.
set -Eeuo pipefail

# Executes in root wherever you inoke i
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

# If no files match no literal match allowed
shopt -s nullglob

# Start all UDP server scripts in the background and stores process ids.
pids_user=()
pids_root=()
log_dir="logs"
mkdir -p "$log_dir"

for udp in src/udp/*_udp_server.py; do
  echo "Starting $udp ..."
  base="$(basename "$udp")"
  if [[ "$base" == "spectrometer_udp_server.py" ]]; then
      sudo python3 "$udp" >"$log_dir/${base%.py}.out" 2>&1 &
      pids_root+=("$!")
  else
      python3 "$udp" >"$log_dir/$(basename "${udp%.py}").out" 2>&1 &
  pids_user+=("$!")
  fi
done

# Clean up background processes when the script exits or is interrupted
cleanup() {
  trap - EXIT INT TERM
  echo "Stopping background servers..."

  term_and_wait() {
    local use_sudo="$1"; shift
    local arr=("$@")
    ((${#arr[@]})) || return 0

    if [[ "$use_sudo" == "sudo" ]]; then
      sudo -n kill -TERM -- "${arr[@]}" 2>/dev/null || true
    else
      kill -TERM -- "${arr[@]}" 2>/dev/null || true
    fi

    local deadline=$((SECONDS + 5))
    for pid in "${arr[@]}"; do
      while kill -0 "$pid" 2>/dev/null; do
        if (( SECONDS >= deadline )); then
          if [[ "$use_sudo" == "sudo" ]]; then
            sudo -n kill -KILL -- "$pid" 2>/dev/null || true
          else
            kill -KILL -- "$pid" 2>/dev/null || true
          fi
          break
        fi
        sleep 0.2
      done
      wait "$pid" 2>/dev/null || true
    done
  }

  term_and_wait "" "${pids_user[@]}"
  term_and_wait "sudo" "${pids_root[@]}"
}
trap cleanup EXIT INT TERM

# Informative message if nothing matched
total=$(( ${#pids_user[@]} + ${#pids_root[@]} ))
if (( total== 0 )); then
  echo "No *_udp_server.py scripts found under src/udp/"
fi


