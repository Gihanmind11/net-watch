"""Regression tests for device type / OS classification.

Covers the bug where Windows hosts (default hostnames like WIN-<hex>,
DESKTOP-*, LAPTOP-*, PC-*) were shown as Android / Mobile/Tablet because the
classifier relied on the ICMP reply TTL, which echo-style stacks can render
as 64.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.scanner import classify_device, guess_os

GW = "192.168.8.1"


class ClassifierTests(unittest.TestCase):
    def assert_classified(self, hostname, ttl, exp_type, exp_os, ip="192.168.8.100"):
        self.assertEqual(classify_device(ip, GW, "", hostname, ttl, ""), exp_type)
        self.assertEqual(guess_os(ttl, hostname, ""), exp_os)

    def test_windows_default_hostnames(self):
        for host in (
            "WIN-JDKBRS07TK2",
            "DESKTOP-ABC123",
            "LAPTOP-7F3D2A",
            "PC-MORGAN",
            "windows-pc-01",
        ):
            with self.subTest(host=host):
                self.assert_classified(host, 64, "Computer", "Windows")

    def test_windows_hostname_without_ttl(self):
        # Even when ICMP is blocked (ttl=None), the hostname wins.
        self.assert_classified("WIN-JDKBRS07TK2", None, "Computer", "Windows")

    def test_android_phone(self):
        self.assert_classified("android-9f3b2c", 64, "Phone", "Android")
        self.assert_classified("Galaxy-S21", 63, "Phone", "Linux/Android")

    def test_apple_devices(self):
        self.assert_classified("iphone-max", 60, "Phone", "iOS")
        self.assert_classified("ipad-pro", 64, "Tablet", "iPadOS")
        self.assert_classified("macbook-air", 64, "Computer", "macOS")

    def test_gateway_stays_gateway(self):
        self.assertEqual(classify_device(GW, GW, "", "homerouter", 255, ""), "Gateway")

    def test_router_from_ttl_255(self):
        self.assertEqual(classify_device("192.168.8.9", GW, "", "wrt", 255, ""), "Router")


if __name__ == "__main__":
    unittest.main(verbosity=2)