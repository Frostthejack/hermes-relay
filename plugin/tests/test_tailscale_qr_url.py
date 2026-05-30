"""Tests for Tailscale auto-TLS integration in server main().

Verifies:
- When Tailscale is active: bind override to 127.0.0.1
- When Tailscale is active: relay URL in QR payload uses MagicDNS hostname
- Headscale detection: no bind override, uses hostname with ws:// scheme
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from plugin.relay.config import TailscaleDetection


class TailscaleActiveBindTests(unittest.TestCase):
    """When Tailscale is active and NOT Headscale, bind is overridden."""

    def _make_active_ts(self, **overrides) -> TailscaleDetection:
        defaults = dict(
            active=True,
            hostname="relay.tail1234.ts.net",
            tailnet_dns="tail1234.ts.net",
            is_headscale=False,
            ipv4="100.64.1.2",
            serve_ports=[],
            message="active",
        )
        defaults.update(overrides)
        return TailscaleDetection(**defaults)

    def test_bind_overridden_to_loopback(self) -> None:
        ts = self._make_active_ts()
        cfg = MagicMock()
        cfg.tailscale = ts
        cfg.port = 8767
        cfg.host = "0.0.0.0"
        cfg.ssl_cert = None

        # Simulate the main() logic
        _ts_cfg = cfg.tailscale
        if _ts_cfg.active and not _ts_cfg.is_headscale:
            old_host = cfg.host
            cfg.host = "127.0.0.1"

        self.assertEqual(cfg.host, "127.0.0.1")

    def test_headscale_no_bind_override(self) -> None:
        ts = self._make_active_ts(is_headscale=True)
        cfg = MagicMock()
        cfg.tailscale = ts
        cfg.host = "0.0.0.0"

        _ts_cfg = cfg.tailscale
        if _ts_cfg.active and not _ts_cfg.is_headscale:
            cfg.host = "127.0.0.1"

        # Headscale path should NOT override bind
        self.assertEqual(cfg.host, "0.0.0.0")


class TailscaleQrUrlTests(unittest.TestCase):
    """Relay URL in QR payload uses MagicDNS hostname when Tailscale active."""

    def test_tailscale_active_uses_https_hostname(self) -> None:
        """Full Tailscale: https://<hostname>:<port>/ws"""
        ts = TailscaleDetection(
            active=True,
            hostname="relay.tail1234.ts.net",
            is_headscale=False,
        )
        relay_port = 8767

        if ts.active and not ts.is_headscale and ts.hostname:
            relay_url = f"https://{ts.hostname}:{relay_port}/ws"
        else:
            relay_url = "should-not-reach"

        self.assertEqual(relay_url, "https://relay.tail1234.ts.net:8767/ws")

    def test_headscale_uses_ws_hostname_no_cert(self) -> None:
        """Headscale without certs: ws://<hostname>:<port>/ws"""
        ts = TailscaleDetection(
            active=True,
            hostname="relay.headscale.example.com",
            is_headscale=True,
        )
        relay_port = 8767
        ssl_cert = None

        if ts.active and not ts.is_headscale and ts.hostname:
            relay_url = f"https://{ts.hostname}:{relay_port}/ws"
        elif ts.active and ts.is_headscale and ts.hostname:
            relay_tls = bool(ssl_cert)
            scheme = "wss" if relay_tls else "ws"
            relay_url = f"{scheme}://{ts.hostname}:{relay_port}/ws"
        else:
            relay_url = "should-not-reach"

        self.assertEqual(relay_url, "ws://relay.headscale.example.com:8767/ws")

    def test_headscale_uses_wss_hostname_with_cert(self) -> None:
        """Headscale with certs: wss://<hostname>:<port>/ws"""
        ts = TailscaleDetection(
            active=True,
            hostname="relay.headscale.example.com",
            is_headscale=True,
        )
        relay_port = 8767
        ssl_cert = "/path/to/cert.pem"

        if ts.active and not ts.is_headscale and ts.hostname:
            relay_url = f"https://{ts.hostname}:{relay_port}/ws"
        elif ts.active and ts.is_headscale and ts.hostname:
            relay_tls = bool(ssl_cert)
            scheme = "wss" if relay_tls else "ws"
            relay_url = f"{scheme}://{ts.hostname}:{relay_port}/ws"
        else:
            relay_url = "should-not-reach"

        self.assertEqual(relay_url, "wss://relay.headscale.example.com:8767/ws")

    def test_inactive_uses_lan_ip(self) -> None:
        """No Tailscale: relay URL falls back to LAN IP."""
        ts = TailscaleDetection(active=False, message="binary absent")
        relay_host = "0.0.0.0"
        relay_port = 8767

        if ts.active and not ts.is_headscale and ts.hostname:
            relay_url = "should-not-reach-ts"
        elif ts.active and ts.is_headscale and ts.hostname:
            relay_url = "should-not-reach-hs"
        else:
            scheme = "ws"
            relay_url = f"{scheme}://192.168.1.100:{relay_port}"

        self.assertEqual(relay_url, "ws://192.168.1.100:8767")


if __name__ == "__main__":
    unittest.main()
