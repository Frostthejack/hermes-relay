"""Tests for config.TailscaleDetection and config.detect_tailscale.

Uses unittest.mock.patch to stub shutil.which and subprocess.run.
"""

from __future__ import annotations

import json
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from plugin.relay.config import TailscaleDetection, detect_tailscale


def _mk_completed(returncode: int, stdout: str = "", stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class TailscaleDetectionDefaultsTests(unittest.TestCase):

    def test_defaults(self) -> None:
        ts = TailscaleDetection()
        self.assertFalse(ts.active)
        self.assertIsNone(ts.hostname)
        self.assertIsNone(ts.tailnet_dns)
        self.assertFalse(ts.is_headscale)
        self.assertIsNone(ts.ipv4)
        self.assertEqual(ts.serve_ports, [])
        self.assertEqual(ts.message, "")


class DetectTailscaleBinaryMissingTests(unittest.TestCase):

    def test_returns_inactive_when_binary_absent(self) -> None:
        with patch("plugin.relay.config.shutil.which", return_value=None):
            result = detect_tailscale()
        self.assertFalse(result.active)
        self.assertEqual(result.message, "binary absent")

    def test_returns_inactive_on_timeout(self) -> None:
        with patch("plugin.relay.config.shutil.which", return_value="/usr/bin/tailscale"), \
             patch("plugin.relay.config.subprocess.run",
                   side_effect=subprocess.TimeoutExpired(cmd="tailscale", timeout=5)):
            result = detect_tailscale()
        self.assertFalse(result.active)
        self.assertIn("timed out", result.message)

    def test_returns_inactive_on_os_error(self) -> None:
        with patch("plugin.relay.config.shutil.which", return_value="/usr/bin/tailscale"), \
             patch("plugin.relay.config.subprocess.run",
                   side_effect=OSError("no such device")):
            result = detect_tailscale()
        self.assertFalse(result.active)
        self.assertIn("os error", result.message)


class DetectTailscaleStatusTests(unittest.TestCase):

    def _status_json(self, **overrides) -> str:
        base = {
            "BackendState": "Running",
            "Self": {
                "HostName": "mybox",
                "DNSName": "mybox.tail1234.ts.net.",
                "TailscaleIPs": ["100.64.1.2", "fd7a:115c:a1e0::1"],
            },
            "CertDomains": ["mybox.tail1234.ts.net"],
        }
        base.update(overrides)
        return json.dumps(base)

    def _serve_json(self) -> str:
        return json.dumps({
            "TCP": {"443": {"HTTPS": True}},
            "Web": {"mybox.tail1234.ts.net:443": {"Handlers": {"/": {}}}},
        })

    def test_active_tailscale_official(self) -> None:
        status = self._status_json()
        serve = self._serve_json()

        def run_side_effect(argv, **kwargs):
            if argv[:3] == ["tailscale", "status", "--json"]:
                return _mk_completed(0, stdout=status)
            if argv[:4] == ["tailscale", "serve", "status", "--json"]:
                return _mk_completed(0, stdout=serve)
            return _mk_completed(1, stderr="unexpected argv")

        with patch("plugin.relay.config.shutil.which", return_value="/usr/bin/tailscale"), \
             patch("plugin.relay.config.subprocess.run", side_effect=run_side_effect):
            result = detect_tailscale()

        self.assertTrue(result.active)
        self.assertEqual(result.hostname, "mybox.tail1234.ts.net")
        self.assertEqual(result.tailnet_dns, "tail1234.ts.net")
        self.assertFalse(result.is_headscale)
        self.assertEqual(result.ipv4, "100.64.1.2")
        self.assertEqual(result.serve_ports, [443])
        self.assertEqual(result.message, "active")

    def test_active_headscale_no_cert_domains(self) -> None:
        status = self._status_json(CertDomains=None)

        def run_side_effect(argv, **kwargs):
            if argv[:3] == ["tailscale", "status", "--json"]:
                return _mk_completed(0, stdout=status)
            if argv[:4] == ["tailscale", "serve", "status", "--json"]:
                return _mk_completed(1, stderr="not available")
            return _mk_completed(1)

        with patch("plugin.relay.config.shutil.which", return_value="/usr/bin/tailscale"), \
             patch("plugin.relay.config.subprocess.run", side_effect=run_side_effect):
            result = detect_tailscale()

        self.assertTrue(result.active)
        self.assertTrue(result.is_headscale)
        self.assertIn("headscale", result.message)

    def test_inactive_when_backend_not_running(self) -> None:
        status = self._status_json(BackendState="Stopped")

        def run_side_effect(argv, **kwargs):
            if argv[:3] == ["tailscale", "status", "--json"]:
                return _mk_completed(0, stdout=status)
            return _mk_completed(1)

        with patch("plugin.relay.config.shutil.which", return_value="/usr/bin/tailscale"), \
             patch("plugin.relay.config.subprocess.run",
                   side_effect=run_side_effect):
            result = detect_tailscale()

        self.assertFalse(result.active)
        self.assertIn("Stopped", result.message)

    def test_inactive_on_nonzero_exit(self) -> None:
        with patch("plugin.relay.config.shutil.which", return_value="/usr/bin/tailscale"), \
             patch("plugin.relay.config.subprocess.run",
                   return_value=_mk_completed(1, stderr="not logged in")):
            result = detect_tailscale()
        self.assertFalse(result.active)
        self.assertEqual(result.message, "not logged in")

    def test_inactive_on_invalid_json(self) -> None:
        with patch("plugin.relay.config.shutil.which", return_value="/usr/bin/tailscale"), \
             patch("plugin.relay.config.subprocess.run",
                   return_value=_mk_completed(0, stdout="not-json")):
            result = detect_tailscale()
        self.assertFalse(result.active)
        self.assertEqual(result.message, "tailscale status returned invalid JSON")

    def test_inactive_on_non_dict_json(self) -> None:
        with patch("plugin.relay.config.shutil.which", return_value="/usr/bin/tailscale"), \
             patch("plugin.relay.config.subprocess.run",
                   return_value=_mk_completed(0, stdout="[1,2,3]")):
            result = detect_tailscale()
        self.assertFalse(result.active)
        self.assertEqual(result.message, "tailscale status JSON was not a dict")

    def test_missing_self_node(self) -> None:
        status = json.dumps({"BackendState": "Running"})

        with patch("plugin.relay.config.shutil.which", return_value="/usr/bin/tailscale"), \
             patch("plugin.relay.config.subprocess.run",
                   return_value=_mk_completed(0, stdout=status)):
            result = detect_tailscale()
        self.assertFalse(result.active)
        self.assertIn("'Self' node is empty", result.message)

    def test_serve_ports_best_effort(self) -> None:
        """serve status failure should not prevent active detection."""
        status = self._status_json()

        def run_side_effect(argv, **kwargs):
            if argv[:3] == ["tailscale", "status", "--json"]:
                return _mk_completed(0, stdout=status)
            return _mk_completed(1, stderr="serve not configured")

        with patch("plugin.relay.config.shutil.which", return_value="/usr/bin/tailscale"), \
             patch("plugin.relay.config.subprocess.run", side_effect=run_side_effect):
            result = detect_tailscale()

        self.assertTrue(result.active)
        self.assertEqual(result.serve_ports, [])

    def test_tailnet_dns_from_hostname(self) -> None:
        status = self._status_json(
            Self={"HostName": "relay", "DNSName": "relay.my-tailnet.ts.net."}
        )

        def run_side_effect(argv, **kwargs):
            if argv[:3] == ["tailscale", "status", "--json"]:
                return _mk_completed(0, stdout=status)
            return _mk_completed(1)

        with patch("plugin.relay.config.shutil.which", return_value="/usr/bin/tailscale"), \
             patch("plugin.relay.config.subprocess.run", side_effect=run_side_effect):
            result = detect_tailscale()

        self.assertTrue(result.active)
        self.assertEqual(result.hostname, "relay.my-tailnet.ts.net")
        self.assertEqual(result.tailnet_dns, "my-tailnet.ts.net")

    def test_ipv4_preference(self) -> None:
        """IPv4 is preferred over IPv6."""
        status = self._status_json(
            Self={"HostName": "h", "TailscaleIPs": ["fd7a::1", "100.64.1.5"]}
        )

        with patch("plugin.relay.config.shutil.which", return_value="/usr/bin/tailscale"), \
             patch("plugin.relay.config.subprocess.run",
                   return_value=_mk_completed(0, stdout=status)):
            result = detect_tailscale()
        self.assertEqual(result.ipv4, "100.64.1.5")

    def test_ipv6_fallback_no_ipv4(self) -> None:
        """When only IPv6 is available, ipv4 stays None."""
        status = self._status_json(
            Self={"HostName": "h", "TailscaleIPs": ["fd7a::1"]}
        )

        with patch("plugin.relay.config.shutil.which", return_value="/usr/bin/tailscale"), \
             patch("plugin.relay.config.subprocess.run",
                   return_value=_mk_completed(0, stdout=status)):
            result = detect_tailscale()
        self.assertIsNone(result.ipv4)


class DetectTailscaleNeverRaisesTests(unittest.TestCase):

    def test_never_raises_on_subprocess_exception(self) -> None:
        with patch("plugin.relay.config.shutil.which", return_value="/usr/bin/tailscale"), \
             patch("plugin.relay.config.subprocess.run",
                   side_effect=Exception("boom")):
            result = detect_tailscale()
        self.assertFalse(result.active)

    def test_never_raises_on_serve_status_exception(self) -> None:
        status = json.dumps({
            "BackendState": "Running",
            "Self": {"HostName": "h", "DNSName": "h.t.ts.net."},
            "CertDomains": ["h.t.ts.net"],
        })

        def run_side_effect(argv, **kwargs):
            if argv[:3] == ["tailscale", "status", "--json"]:
                return _mk_completed(0, stdout=status)
            raise Exception("serve blew up")

        with patch("plugin.relay.config.shutil.which", return_value="/usr/bin/tailscale"), \
             patch("plugin.relay.config.subprocess.run", side_effect=run_side_effect):
            result = detect_tailscale()
        self.assertTrue(result.active)


if __name__ == "__main__":
    unittest.main()
