#!/bin/bash
# Build the test container, start it, run the integration tests inside it.
#
# Needs a working docker daemon and privileged mode: the tests exercise real
# systemd units, so systemd has to run as PID 1 inside the container. Nothing
# on the host is touched - the repository is mounted read-only.
#
# The image is deleted again afterwards, because it is several hundred megabytes
# that are of no use between runs. Set KEEP_IMAGE=1 to keep it, which saves the
# download and the build when the next run follows soon.
set -euo pipefail

IMAGE=urbackup-gated-tests
CONTAINER=urbackup-gated-tests-run
KEEP_IMAGE=${KEEP_IMAGE:-0}

REPO=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)

command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }
docker info >/dev/null 2>&1 || {
    echo "the docker daemon is not reachable - start it, or add yourself to the docker group" >&2
    exit 1
}

echo "== building $IMAGE"
docker build -t "$IMAGE" -f "$REPO/tests/container/Dockerfile" "$REPO/tests/container"

docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
cleanup() {
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    if [ "$KEEP_IMAGE" = 1 ]; then
        echo "== keeping image $IMAGE (KEEP_IMAGE=1)"
    else
        docker image rm -f "$IMAGE" >/dev/null 2>&1 || true
    fi
}
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

# "docker run -d" returns once the container runs, not once systemd inside it
# answers, so the first few attempts are expected to fail. A container is also
# routinely "degraded" because some system units have nothing to do in here;
# only a hard failure to boot matters, which is why dbus is the criterion.
BOOT_TIMEOUT=60
waited=0
until docker exec "$CONTAINER" systemctl is-active --quiet dbus.service 2>/dev/null; do
    waited=$((waited + 1))
    if [ "$waited" -ge "$BOOT_TIMEOUT" ]; then
        echo "systemd did not come up inside the container within ${BOOT_TIMEOUT}s" >&2
        docker logs "$CONTAINER" >&2 || true
        exit 1
    fi
    sleep 1
done
docker exec "$CONTAINER" systemctl is-system-running --wait >/dev/null 2>&1 || true

echo "== running tests"
docker exec "$CONTAINER" /src/tests/container/inside/run.sh
