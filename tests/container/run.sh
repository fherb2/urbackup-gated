#!/bin/bash
# Build the test container, start it, run the integration tests inside it.
#
# Needs a working docker daemon and privileged mode: the tests exercise real
# systemd units, so systemd has to run as PID 1 inside the container. Nothing
# on the host is touched - the repository is mounted read-only.
set -euo pipefail

IMAGE=urbackup-gated-tests
CONTAINER=urbackup-gated-tests-run

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)

command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }
docker info >/dev/null 2>&1 || {
    echo "the docker daemon is not reachable - start it, or add yourself to the docker group" >&2
    exit 1
}

echo "== building $IMAGE"
docker build -t "$IMAGE" -f "$REPO/tests/container/Dockerfile" "$REPO/tests/container"

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

echo "== starting $CONTAINER"
docker run -d --name "$CONTAINER" \
    --privileged \
    --cgroupns=host \
    -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
    --tmpfs /run \
    --tmpfs /run/lock \
    -v "$REPO:/src:ro" \
    "$IMAGE" >/dev/null

# A container is routinely "degraded" because some system units have nothing to
# do here; only a hard failure to boot matters.
docker exec "$CONTAINER" systemctl is-system-running --wait >/dev/null 2>&1 || true
if ! docker exec "$CONTAINER" systemctl is-active --quiet dbus.service; then
    echo "systemd did not come up inside the container" >&2
    docker logs "$CONTAINER" >&2 || true
    exit 1
fi

echo "== running tests"
docker exec "$CONTAINER" /src/tests/container/inside/run.sh
