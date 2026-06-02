#!/usr/bin/env python3
"""
Static analysis validator for ActionRateLimiter.kt rate limit configuration.

Parses the Kotlin source as plain text and verifies the rate limit table
matches the specification exactly. No Android SDK or Kotlin compiler needed.

Usage:
    python validate_rate_limiter.py [path_to_ActionRateLimiter.kt]

Exit code 0 = all checks pass, 1 = one or more failures.
"""

import re
import sys
from pathlib import Path

# ── Spec: path -> (max_actions, window_seconds) ──────────────────────────────
SPEC = {
    "/tap":          (30, 10),
    "/tap_text":     (10, 10),
    "/type":         (10, 10),
    "/swipe":        (20, 10),
    "/send_sms":     ( 3, 60),
    "/call":         ( 2, 60),
    "/screen":       (10, 10),
    "/screenshot":   ( 5, 10),
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_kotlin(path: str) -> str:
    p = Path(path)
    if not p.exists():
        print(f"FATAL: file not found: {p}")
        sys.exit(1)
    return p.read_text(encoding="utf-8")


def extract_rate_limits(source: str) -> dict[str, tuple[int, int]]:
    """Parse the `limits` mapOf(...) block from ActionRateLimiter.kt."""
    # Grab everything between `private val limits = mapOf(` and the closing `)`
    # We do a simple brace-balance scan.
    anchor = "private val limits = mapOf("
    start = source.find(anchor)
    if start == -1:
        print("FATAL: could not find `private val limits = mapOf(` in source")
        sys.exit(1)

    # Scan forward to find the matching closing paren
    depth = 0
    i = start + len(anchor) - 1  # position at the opening `(`
    block_start = i
    for i in range(block_start, len(source)):
        ch = source[i]
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth == 0:
                block = source[block_start:i+1]
                break
    else:
        print("FATAL: unclosed mapOf block")
        sys.exit(1)

    # Now extract individual entries:  "path" to RateLimit(maxActions = N, windowMs = M, ...)
    # Note: Kotlin allows underscore separators in numeric literals (10_000, 60_000)
    pattern = re.compile(
        r'^\s+"(/\w+)"\s+to\s+RateLimit\s*\(\s*'
        r'maxActions\s*=\s*([\d_]+)\s*,\s*'
        r'windowMs\s*=\s*([\d_]+)\s*,',
        re.MULTILINE,
    )

    limits: dict[str, tuple[int, int]] = {}
    for m in pattern.finditer(block):
        path = m.group(1)
        max_actions = int(m.group(2).replace("_", ""))
        window_ms = int(m.group(3).replace("_", ""))
        limits[path] = (max_actions, window_ms // 1000)  # convert ms → seconds

    return limits


def check_bot_detection(source: str) -> list[str]:
    """Verify bot-pattern detection is present."""
    issues: list[str] = []

    # Check variance threshold constant (2500 = 50ms ^ 2)
    if "AUTOMATED_PATTERN_VARIANCE_THRESHOLD_MS2" not in source:
        issues.append("BOT: missing AUTOMATED_PATTERN_VARIANCE_THRESHOLD_MS2 constant")
    elif "2500" not in source:
        issues.append("BOT: AUTOMATED_PATTERN_VARIANCE_THRESHOLD_MS2 is not 2500 (50ms^2)")

    # Check that the bot detection logic exists (variance-based)
    if "variance" not in source.lower():
        issues.append("BOT: no variance calculation found in bot detection")

    # Check that < 5 samples short-circuits detection (need 5 samples minimum)
    if "size >= 5" not in source and "size>=5" not in source:
        issues.append("BOT: no minimum-sample check (need 5 samples for variance)")

    return issues


def check_error_code(source: str) -> list[str]:
    """Verify the 429 response includes error_code=rate_limited."""
    issues: list[str] = []

    # Check 429 status code is used
    if "429" not in source:
        issues.append("ERR: no 429 status code found in response")

    # Check error_code = "rate_limited" is in the response
    if '"rate_limited"' not in source and "'rate_limited'" not in source:
        issues.append("ERR: no error_code 'rate_limited' in 429 response")

    return issues


def check_integration(bridge_source: str) -> list[str]:
    """Verify BridgeCommandHandler.kt calls rateLimiter.tryAcquire()."""
    issues: list[str] = []

    if "rateLimiter" not in bridge_source:
        issues.append("INT: no rateLimiter field in BridgeCommandHandler")

    if "tryAcquire" not in bridge_source:
        issues.append("INT: tryAcquire() not called in BridgeCommandHandler")

    return issues


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    kt_path = sys.argv[1] if len(sys.argv) > 1 else (
        Path(__file__).resolve().parent
        / "app/src/main/kotlin/com/hermesandroid/relay/bridge/ActionRateLimiter.kt"
    )
    bridge_path = Path(kt_path).parent.parent / "network/handlers/BridgeCommandHandler.kt"

    source = load_kotlin(str(kt_path))
    bridge_source = load_kotlin(str(bridge_path)) if bridge_path.exists() else ""

    all_issues: list[str] = []
    checks_passed = 0
    checks_total = 0

    # ── 1. Rate limit table completeness & correctness ───────────────
    print("=" * 64)
    print("  Rate Limit Configuration Check")
    print("=" * 64)

    actual = extract_rate_limits(source)

    # Check all 8 paths exist
    checks_total += 1
    missing_paths = set(SPEC) - set(actual)
    if missing_paths:
        all_issues.append(f"MISSING PATHS: {missing_paths}")
        print(f"  FAIL — missing paths: {missing_paths}")
    else:
        checks_passed += 1
        print(f"  PASS — all 8 paths present")

    # Check each path's values
    for path, (spec_max, spec_secs) in SPEC.items():
        checks_total += 1
        if path not in actual:
            continue  # already reported above
        actual_max, actual_secs = actual[path]
        errors = []
        if actual_max != spec_max:
            errors.append(f"maxActions {actual_max} != spec {spec_max}")
        if actual_secs != spec_secs:
            errors.append(f"window {actual_secs}s != spec {spec_secs}s")
        if errors:
            all_issues.append(f"RATE {path}: {', '.join(errors)}")
            print(f"  FAIL — {path}: {', '.join(errors)}")
        else:
            checks_passed += 1
            print(f"  PASS — {path}: {actual_max}/{actual_secs}s")

    # ── 2. Bot-pattern detection ─────────────────────────────────────
    print()
    print("=" * 64)
    print("  Bot-Pattern Detection Check")
    print("=" * 64)

    bot_issues = check_bot_detection(source)
    checks_total += 1
    if bot_issues:
        all_issues.extend(bot_issues)
        for i in bot_issues:
            print(f"  FAIL — {i}")
    else:
        checks_passed += 1
        print("  PASS — bot-pattern detection present (50ms variance threshold)")

    # ── 3. 429 response with error_code ──────────────────────────────
    print()
    print("=" * 64)
    print("  429 Response Check (ActionRateLimiter.kt)")
    print("=" * 64)
    # The 429 response lives in BridgeCommandHandler.kt, not ActionRateLimiter.kt
    # We check it there below. Here we check only the limiter's own logging.
    print("  INFO — 429 response is in BridgeCommandHandler.kt (checked below)")

    # ── 4. BridgeCommandHandler integration ───────────────────────────
    if bridge_source:
        print()
        print("=" * 64)
        print("  BridgeCommandHandler Integration Check")
        print("=" * 64)

        int_issues = check_integration(bridge_source)
        checks_total += 1
        if int_issues:
            all_issues.extend(int_issues)
            for i in int_issues:
                print(f"  FAIL — {i}")
        else:
            checks_passed += 1
            print("  PASS — rateLimiter.tryAcquire() called in dispatch()")

        # 429 + error_code check
        err_issues = check_error_code(bridge_source)
        checks_total += 1
        if err_issues:
            all_issues.extend(err_issues)
            for i in err_issues:
                print(f"  FAIL — {i}")
        else:
            checks_passed += 1
            print('  PASS — 429 response with error_code="rate_limited"')

        # Ordering: rate limiter after blocklist
        checks_total += 1
        blocklist_pos = bridge_source.find("blocklistAllowed")
        ratelimit_pos = bridge_source.find("rl.tryAcquire")
        if blocklist_pos > 0 and ratelimit_pos > 0 and ratelimit_pos > blocklist_pos:
            checks_passed += 1
            print("  PASS — rate limiter called after blocklist check")
        elif blocklist_pos > 0 and ratelimit_pos > 0:
            all_issues.append("ORDER: rate limiter before blocklist check")
            print("  FAIL — rate limiter called BEFORE blocklist check")
        else:
            all_issues.append("ORDER: could not verify ordering")
            print("  FAIL — could not verify ordering")
    else:
        print(f"\n  SKIP — BridgeCommandHandler.kt not found at {bridge_path}")

    # ── Summary ───────────────────────────────────────────────────────
    print()
    print("=" * 64)
    print(f"  RESULT: {checks_passed}/{checks_total} checks passed")
    print("=" * 64)

    if all_issues:
        print(f"\n  FAILURES ({len(all_issues)}):")
        for issue in all_issues:
            print(f"    - {issue}")
        print()
        sys.exit(1)
    else:
        print("\n  ALL CHECKS PASSED -- rate limit config matches spec.\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
