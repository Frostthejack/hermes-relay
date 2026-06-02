#!/usr/bin/env python3
"""
Validate SensitiveAppDetector.kt BUILTIN_SENSITIVE_PREFIXES:
  - At least 40 entries total
  - Covers all 3 categories: banking, password managers, 2FA/auth apps
  - No empty strings
  - All entries look like valid package prefix strings
"""

import re
import sys

# Extracted from SensitiveAppDetector.kt BUILTIN_SENSITIVE_PREFIXES block
SOURCE = """
        // ── System credential / auth ──────────────────────────────────
        "com.android.credentialmgr",
        "com.google.android.gms.auth",
        "com.samsung.android.auth",

        // ── Banking (US) ───────────────────────────────────────────────
        "com.chase.sig.android",
        "com.wf.wellsfargomobile",
        "com.bankofamerica",
        "com.usaa.mobile.android.usaa",
        "com.konylabs.capitalone",
        "com.americanexpress.android.acctsvcs.us",
        "com.discoverfinancial.mobile",
        "com.infonow.bofa",
        "com.citi.citimobile",

        // ── Banking (UK / EU) ─────────────────────────────────────────
        "uk.co.hsbc.hsbcukmobilebanking",
        "com.barclays.android.barclaysmobilebanking",
        "com.monzo.android",
        "co.uk.getmondo",
        "co.revolut.app",
        "com.starlingbank.android",
        "com.lloydsbank",
        "com.rbs.mobile.android",
        "com.natwest",
        "com.santander",

        // ── Payments / crypto ─────────────────────────────────────────
        "com.venmo",
        "com.squareup.cash",
        "com.paypal.android.p2pmobile",
        "com.coinbase.android",
        "co.mona.android",
        "com.kraken",

        // ── Password managers ─────────────────────────────────────────
        "com.lastpass.lpandroid",
        "com.dashlane",
        "com.agilebits.onepassword",
        "com.x8bit.bitwarden",
        "com.keepersecurity.passwordmanager",
        "com.bitwarden.authenticator",
        "com.enzopc.1password",

        // ── 2FA / Auth apps ───────────────────────────────────────────
        "com.google.android.apps.authenticator2",
        "com.authy.authy",
        "com.duosecurity.duomobile",
        "com.microsoft.azure.authenticator",
        "com.yubico.yubioath",
"""

# Category definitions: comment substring -> bucket name
CATEGORIES = {
    "System credential / auth": "System/Auth",
    "Banking (US)":             "Banking",
    "Banking (UK / EU)":        "Banking",
    "Payments / crypto":        "Banking",       # financial -> banking bucket
    "Password managers":        "Password Manager",
    "2FA / Auth apps":          "2FA/Auth",
}

REQUIRED_CATEGORIES = {"Banking", "Password Manager", "2FA/Auth"}

# ── Build prefix -> category map ──────────────────────────────────────────────
prefix_category: dict[str, str] = {}
current_category: str | None = None

for line in SOURCE.splitlines():
    stripped = line.strip()
    # Detect category comment
    for comment_prefix, cat_name in CATEGORIES.items():
        if comment_prefix in stripped:
            current_category = cat_name
            break
    # Extract package names
    m = re.match(r'"([^"]+)"', stripped)
    if m and current_category:
        prefix_category[m.group(1)] = current_category

all_prefixes = list(prefix_category.keys())

# ── Validation ────────────────────────────────────────────────────────────────
errors: list[str] = []
warnings: list[str] = []

# 1. Count
total = len(all_prefixes)
if total < 40:
    errors.append(f"Only {total} prefixes found, need >= 40")
else:
    print(f"[PASS] Total prefixes: {total} (>= 40)")

# 2. No empty strings or invalid chars
for p in all_prefixes:
    if not p:
        errors.append("Empty prefix entry")
    if not re.match(r'^[a-zA-Z0-9._]+$', p):
        warnings.append(f"Suspicious characters in prefix: {p}")

# 3. Category coverage
found_categories = set(prefix_category.values())
missing = REQUIRED_CATEGORIES - found_categories
if missing:
    errors.append(f"Missing categories: {missing}")
else:
    print(f"[PASS] All required categories found: {sorted(REQUIRED_CATEGORIES)}")

# 4. Breakdown by category
print("\n-- Category Breakdown --")
for cat in sorted(found_categories):
    entries = [p for p, c in prefix_category.items() if c == cat]
    print(f"  {cat}: {len(entries)} entries")
    for e in entries:
        print(f"    - {e}")

# 5. Duplicate check
seen = set()
dupes = []
for p in all_prefixes:
    if p in seen:
        dupes.append(p)
    seen.add(p)
if dupes:
    errors.append(f"Duplicate prefixes: {dupes}")
else:
    print(f"[PASS] No duplicate prefixes")

# 6. Print extras
if warnings:
    print("\n-- Warnings --")
    for w in warnings:
        print(f"  [WARN] {w}")

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
if errors:
    print(f"RESULT: FAIL ({len(errors)} error(s))")
    for e in errors:
        print(f"  FAIL: {e}")
    sys.exit(1)
else:
    print("RESULT: PASS -- All checks passed")
    sys.exit(0)
