#!/usr/bin/env bash
# Only signals a verified, dedicated Fullstack process group; never a shared shell PGID.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
PIDFILE="$ROOT/run/bapeten-fullstack.pid"
MY_UID="$(id -u)"
[[ -f "$PIDFILE" ]] || { echo 'Tidak ada PID file. Periksa orphan via patch_v062/cleanup_orphan_workers.sh.'; exit 0; }
PID="$(cat "$PIDFILE" 2>/dev/null || true)"
[[ "$PID" =~ ^[0-9]+$ ]] || { echo 'ERROR: PID file tidak valid.' >&2; exit 1; }

# All live, non-zombie processes in PGID == launcher PID owned by current account.
group_pids() {
  ps -eo pid=,pgid=,uid=,stat= | awk -v gp="$PID" -v uid="$MY_UID" '$2 == gp && $3 == uid && $4 !~ /^Z/ {print $1}'
}
project_proc() {
  local p="$1" cmd cwd
  cwd="$(readlink -f "/proc/$p/cwd" 2>/dev/null || true)"
  [[ "$cwd" == "$BACKEND" ]] || return 1
  cmd="$(tr '\0' ' ' < "/proc/$p/cmdline" 2>/dev/null || true)"
  [[ "$cmd" == *'uvicorn app.main:app'* || "$cmd" == *'multiprocessing.'* || "$cmd" == *'--multiprocessing-fork'* ]]
}

group_safe=0
while read -r p; do
  [[ -n "$p" ]] || continue
  if project_proc "$p"; then group_safe=1; break; fi
done < <(group_pids)

if [[ "$group_safe" -eq 1 ]]; then
  echo "Menghentikan grup BAPETEN Fullstack: PGID=$PID (Uvicorn + forkserver + OCR workers)."
  kill -TERM -- "-$PID" 2>/dev/null || true
  for _ in $(seq 1 20); do
    [[ -z "$(group_pids)" ]] && break
    sleep 1
  done
  if [[ -n "$(group_pids)" ]]; then
    # Verify there is still a Fullstack process in group before sending SIGKILL.
    safe_again=0
    while read -r p; do
      [[ -n "$p" ]] || continue
      if project_proc "$p"; then safe_again=1; break; fi
    done < <(group_pids)
    if [[ "$safe_again" -ne 1 ]]; then
      echo 'ERROR: anggota grup tersisa tidak terverifikasi. Periksa manual.' >&2; exit 1
    fi
    echo 'Masih berjalan setelah 20 detik; menghentikan grup dengan SIGKILL.'
    kill -KILL -- "-$PID" 2>/dev/null || true
    sleep 2
  fi
  if [[ -n "$(group_pids)" ]]; then
    echo 'ERROR: grup masih aktif. PID file dipertahankan.' >&2; exit 1
  fi
  rm -f "$PIDFILE"
  echo 'Selesai. Semua proses hidup dalam grup telah berhenti.'
  exit 0
fi

# Fallback: old launcher did not use setsid and might share a PGID with other jobs.
# NEVER send a negative-PGID signal for that launcher.
if ! kill -0 "$PID" 2>/dev/null; then
  rm -f "$PIDFILE"
  echo 'Uvicorn lama sudah mati; mungkin masih ada worker yatim. Gunakan cleanup_orphan_workers.sh.'
  exit 0
fi
if ! project_proc "$PID"; then
  echo "ERROR: PID $PID tidak terbukti milik BAPETEN; tidak akan dihentikan." >&2
  exit 1
fi
echo "Launcher lama: menghentikan PID Uvicorn $PID saja (grup bersama tidak disentuh)."
kill -TERM "$PID"
for _ in $(seq 1 15); do
  if ! kill -0 "$PID" 2>/dev/null; then break; fi
  state="$(ps -p "$PID" -o stat= 2>/dev/null || true)"
  [[ "$state" == Z* ]] && break
  sleep 1
done
if kill -0 "$PID" 2>/dev/null; then
  state="$(ps -p "$PID" -o stat= 2>/dev/null || true)"
  [[ "$state" == Z* ]] || { echo "ERROR: PID $PID belum berhenti." >&2; exit 1; }
fi
rm -f "$PIDFILE"
echo 'Uvicorn berhenti. Bersihkan proses yatim secara terpisah.'
