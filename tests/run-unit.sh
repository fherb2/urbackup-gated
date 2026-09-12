#!/bin/sh
# Run the unit tests. No root, no container, no extra packages.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
exec python3 -m unittest discover -s tests/unit -t tests/unit -v "$@"
