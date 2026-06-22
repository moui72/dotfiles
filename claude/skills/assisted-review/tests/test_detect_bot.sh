#!/usr/bin/env bash
# Tests for scripts/detect-bot.sh — pattern rules + bots.txt + user-bots.txt merge.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DETECT="$SKILL_DIR/scripts/detect-bot.sh"

PASS=0
FAIL=0

assert_bot() {
    local login="$1"
    local desc="$2"
    if "$DETECT" "$login" >/dev/null 2>&1; then
        echo "  ok   — $desc ($login)"
        PASS=$((PASS + 1))
    else
        echo "  FAIL — $desc ($login)"
        FAIL=$((FAIL + 1))
    fi
}

refute_bot() {
    local login="$1"
    local desc="$2"
    if "$DETECT" "$login" >/dev/null 2>&1; then
        echo "  FAIL — $desc ($login)"
        FAIL=$((FAIL + 1))
    else
        echo "  ok   — $desc ($login)"
        PASS=$((PASS + 1))
    fi
}

echo "detect-bot.sh"

# Pattern rules
assert_bot "renovate[bot]"        "ends with [bot]"
assert_bot "RENOVATE[bot]"        "case-insensitive [bot]"
assert_bot "sa-deployer"          "sa- prefix"
assert_bot "ci-automation"        "*-automation suffix"
assert_bot "foo-automation-bar"   "-automation- segment"

# bots.txt match
assert_bot "dependabot"           "bundled bots.txt match"

# Negative cases
refute_bot "alice"                "ordinary user not matched"
refute_bot "automation-prefix"    "prefix automation- does not match"

# user-bots.txt merge — write a temp entry, verify, clean up
USER_BOTS="$SKILL_DIR/user-bots.txt"
USER_BOTS_BACKUP=""
if [ -f "$USER_BOTS" ]; then
    USER_BOTS_BACKUP="$(mktemp)"
    cp "$USER_BOTS" "$USER_BOTS_BACKUP"
fi
trap '[ -n "$USER_BOTS_BACKUP" ] && mv "$USER_BOTS_BACKUP" "$USER_BOTS" || rm -f "$USER_BOTS"' EXIT

echo "test-local-bot-xyz" > "$USER_BOTS"
assert_bot "test-local-bot-xyz"   "user-bots.txt match"
refute_bot "test-local-bot-abc"   "different login in user-bots.txt not matched"

echo
echo "passed: $PASS  failed: $FAIL"
exit $FAIL
