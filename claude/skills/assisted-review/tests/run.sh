#!/usr/bin/env bash
# Run all assisted-review unit tests. Exits non-zero on any failure.
# Wired into the pre-commit hook (hooks/pre-commit).

set -uo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$TESTS_DIR"

fail=0

echo "== python =="
if ! python3 -m unittest discover -s "$TESTS_DIR" -p "test_*.py" -t "$TESTS_DIR" -v; then
    fail=1
fi

echo
echo "== shell =="
for t in "$TESTS_DIR"/test_*.sh; do
    [ -f "$t" ] || continue
    if ! bash "$t"; then
        fail=1
    fi
done

echo
if [ "$fail" -eq 0 ]; then
    echo "all tests passed"
else
    echo "TESTS FAILED" >&2
fi
exit "$fail"
