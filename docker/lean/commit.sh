#!/usr/bin/env bash
set -euo pipefail

# One-time, no-network final deployment. Source the prepared volume directly
# into an immutable staging image. The final Dockerfile copies only vetted
# runtime files and labels; it never resolves dependencies again.
prepared=mathagent-s09-lean-r3
staging=mathagent-lean-staging
image=mathagent-lean:4.19.0
repo_root="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
artifact_dir="$repo_root/artifacts/lean-image-commit-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$artifact_dir"
if docker inspect "$staging" >/dev/null 2>&1; then
  echo "staging container already exists; inspect it before continuing" >&2
  exit 1
fi
container_id="$(docker create --name "$staging" -v "$prepared":/prepared:ro \
  ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852 \
  sh -ec 'mkdir -p /opt/s09; tar -C /prepared --exclude="packages-*drift*" -cf - lean-4.19.0-linux mathlib | tar -C /opt/s09 -xf -; ln -s /opt/s09/lean-4.19.0-linux /opt/lean')"
trap 'docker rm -f "$staging" >/dev/null 2>&1 || true' EXIT
docker start -a "$container_id" >/dev/null
docker commit   --change 'ENV HOME=/opt/s09/home'   --change 'ENV PATH=/opt/lean/bin:/usr/local/bin:/usr/bin:/bin'   "$container_id" mathagent-lean-stage-base:4.19.0
build_hash="$(uv run python -c 'import json,sys; print(json.load(open(sys.argv[1]))["build_manifest_sha256"])' "$(dirname "$0")/build-manifest.json")"
docker build --pull=false --build-arg "BUILD_MANIFEST_SHA256=$build_hash" \
  -f "$(dirname "$0")/Dockerfile" -t "$image" "$(dirname "$0")"
docker image inspect "$image" --format '{{.Id}}' > "$artifact_dir/image-id.txt"
