#!/usr/bin/env bash
set -euo pipefail

# Source and native recursive #print axioms audit arrive on stdin from the
# registered template. No caller-selected command or dependency resolution.
cd /opt/s09/mathlib
LEAN_PATH=/opt/s09/mathlib/.lake/build/lib/lean
for path in /opt/s09/mathlib/.lake/packages/*/.lake/build/lib/lean; do
  if [ -d "$path" ]; then LEAN_PATH="$LEAN_PATH:$path"; fi
done
export LEAN_PATH
code=0
/opt/lean/bin/lean --stdin || code=$?
if [ -r /sys/fs/cgroup/memory.peak ]; then
  printf 'S09_MEMORY_PEAK_BYTES=%s\n' "$(cat /sys/fs/cgroup/memory.peak)" >&2
fi
if [ -r /sys/fs/cgroup/cpu.stat ]; then
  while read -r key value; do
    if [ "$key" = usage_usec ]; then
      printf 'S09_CPU_USAGE_USEC=%s\n' "$value" >&2
    fi
  done < /sys/fs/cgroup/cpu.stat
fi
exit "$code"
