#!/usr/bin/env bash
set -euo pipefail

status_dir=/out
status_file="$status_dir/status.json"
log_file="$status_dir/prepare.log"
run_id="${S09_RUN_ID:-faithful-s09-prepare-manual}"
container_name="${S09_CONTAINER_NAME:-mathagent-lean-prepare}"
mkdir -p "$status_dir"
: > "$log_file"
# Capture all command output at the file descriptor level. Do not add per-command
# redirections; they bypass this tee and hid the r5 failing stderr.
exec > >(tee -a "$log_file") 2> >(tee -a "$log_file" >&2)
phase=starting
count=0
started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
write_status() {
  local result="$1"
  local message="$2"
  local updated tmp
  updated="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  tmp="$status_file.tmp"
  {
    printf '{"schema_version":1,"run_id":"%s","container":"%s",' "$run_id" "$container_name"
    printf '"phase":"%s","completed_steps":%s,"started_at":"%s","updated_at":"%s",' "$phase" "$count" "$started_at" "$updated"
    printf '"result":"%s","message":"%s","log":"/out/prepare.log"}\n' "$result" "$message"
  } > "$tmp"
  mv "$tmp" "$status_file"
}
step() {
  phase="$1"
  count="$((count + 1))"
  printf '{"phase":"%s","step":%s,"at":"%s"}\n' "$phase" "$count" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  write_status running ""
}
fail_trap() {
  local code=$?
  if [ "$code" -ne 0 ]; then
    phase=failed
    write_status failed "exit_code=$code"
  fi
}
trap fail_trap EXIT

step apt-install
export DEBIAN_FRONTEND=noninteractive
if ! command -v zstd >/dev/null || ! command -v git >/dev/null; then
  apt-get update
  apt-get install -y --no-install-recommends ca-certificates curl git python3 zstd xxd
fi

step toolchain-check
LEAN_ROOT=/prepared/lean-4.19.0-linux
if [ ! -x "$LEAN_ROOT/bin/lean" ]; then
  test "$(sha256sum /asset/lean-4.19.0-linux.tar.zst | cut -d' ' -f1)" = "6fe3ce97a58f44e2b3567d455b994eacec5bfe9ae7774f2a573444480ba813fe"
  tar --zstd --no-same-owner -xf /asset/lean-4.19.0-linux.tar.zst -C /prepared
fi
ln -sfn "$LEAN_ROOT" /opt/lean
LEAN_VERSION="$(/opt/lean/bin/lean --version)"
case "$LEAN_VERSION" in
  "Lean (version 4.19.0, x86_64-unknown-linux-gnu, commit 6caaee842e94, Release)") ;;
  *) echo "unexpected Lean identity: $LEAN_VERSION" >&2; exit 21 ;;
esac
/opt/lean/bin/lake --version
chmod -R a+rX "$LEAN_ROOT"

step mathlib-lock
mkdir -p /prepared/home
cd /prepared
if [ ! -d mathlib/.git ]; then
  git init mathlib
  cd mathlib
  git remote add origin https://github.com/leanprover-community/mathlib4.git
else
  cd mathlib
  git remote set-url origin https://github.com/leanprover-community/mathlib4.git
fi
MATHLIB_COMMIT=c44e0c8ee63ca166450922a373c7409c5d26b00b
git fetch --depth 1 origin "$MATHLIB_COMMIT"
git checkout --detach FETCH_HEAD
git restore --source="$MATHLIB_COMMIT" --staged --worktree -- lean-toolchain lake-manifest.json
test "$(git rev-parse HEAD)" = "$MATHLIB_COMMIT"
test "$(cat lean-toolchain)" = "leanprover/lean4:v4.19.0"
git diff --quiet "$MATHLIB_COMMIT" -- lean-toolchain lake-manifest.json
echo "locked Mathlib commit and toolchain verified: $MATHLIB_COMMIT"

step mathlib-cache
cd /prepared/mathlib
# No lake update. The checked-in v4.19.0 manifest fixes every dependency revision.
/opt/lean/bin/lake exe cache get
# A Docker interruption may leave an existing .olean partially written. Restore
# every file from the pinned downloaded archives instead of trusting timestamps.
/opt/lean/bin/lake exe cache unpack!

step mathlib-probe-build
/opt/lean/bin/lake build Mathlib.Tactic

step freeze
chown -R 65534:65534 /prepared
chmod -R a-w /prepared
step complete
write_status success ""
