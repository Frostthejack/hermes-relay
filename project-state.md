---
date: 2026-05-30
status: active
phase: 0
project: hermes-relay-hardening
tags: [security, hardening, fork]
---

# Hermes-Relay Hardening Project State

## What This Is
Security hardening fork of [Codename-11/hermes-relay](https://github.com/Codename-11/hermes-relay) — an AI agent remote control system for Android and desktop.

## Fork Details
- **Upstream**: https://github.com/Codename-11/hermes-relay
- **Fork**: https://github.com/frostthejack/hermes-relay
- **Local**: `/c/Users/luned/Documents/Projects/hermes-relay-hardening/`
- **Board**: `hermes-relay` kanban
- **Vault**: `/c/Users/luned/Vault/Encephalon-Mageia/Projects/Personal/hermes-relay-hardening/`

## Critical Issues Being Fixed
1. curl-pipe installer (no signature verification)
2. Bootstrap monkey-patching (sys.meta_path hook into aiohttp)
3. Default plaintext ws:// (no TLS)
4. 6-char pairing codes (~26 bits entropy)
5. Hermes API key in QR code
6. No Android rate limiting
7. /send_intent escape hatch
8. No persistent audit log

## Phases

### Phase 0: Project Initiation ✅
- [x] Kanban board created
- [x] Repo forked and cloned
- [x] Project-state.md created
- [ ] Cron jobs configured

### Phase 1: Immediate Wins
- [ ] Signed releases via cosign keyless
- [ ] Android rate limiting
- [ ] FLAG_SECURE for sensitive apps
- [ ] Sensitive app detection
- [ ] Close /pairing endpoint

### Phase 2: Core Hardening
- [ ] Tailscale auto-TLS
- [ ] Android certificate pinning
- [ ] Full-screen intent confirmations
- [ ] Time-bound action grants

### Phase 3: Long-Term
- [ ] Ed25519 device identity
- [ ] Plugin API (upstream)
- [ ] Persistent audit log + anomaly detection
- [ ] Command allowlisting
- [ ] Server-side anomaly detection

## Research Documents
- `C:\Users\luned\tailscale-hermes-relay-research.md`
- `C:\Users\luned\ed25519-device-identity-research.md`
- `C:\Users\luned\hermes-relay-signed-release-pipeline.md`
- `C:\Users\luned\hermes-relay-security-research.md`
- `C:\Users\luned\plan-review-implementation.md`
- `C:\Users\luned\plan-review-security.md`

## Secrets
| Variable | Location | Notes |
|----------|----------|-------|
| `GH_TOKEN` | Bitwarden | GitHub API access |
| `OPENROUTER_API_KEY` | Bitwarden | AI model access |

## Key Architectural Decisions
- **Treat /screen and /clipboard as destructive** (reviewer recommendation)
- **Use Tailscale identity headers** instead of Ed25519 for initial auth (simpler)
- **Ed25519 deferred** until Tailscale stable; key backup plan required
- **Plugin API must be upstreamed** to hermes-agent; use shim in fork
- **Plugin allowlist + signing** required to prevent supply-chain attacks

## Residual Risk Warning
Even with all fixes: HIGH residual risk from LLM prompt injection. The LLM remains an untrusted command authorizer. Plan makes system "defensible for personal tool" — NOT "secure against compromised LLM".
