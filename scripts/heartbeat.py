#!/usr/bin/env python3
"""Run on the Docker host via systemd; only signal health when checks pass."""
import os
import urllib.request

def check(url):
    with urllib.request.urlopen(url, timeout=8) as response:
        if response.status != 200:
            raise RuntimeError("Unhealthy service")

check("http://127.0.0.1:8000/readyz")
check("http://127.0.0.1:9090/-/ready")
url = os.environ["WATCHDOG_URL"]
if not url.startswith("https://"):
    raise ValueError("WATCHDOG_URL must use HTTPS")
request = urllib.request.Request(url, method="POST",
    headers={"Authorization": "Bearer " + os.environ["WATCHDOG_TOKEN"]}, data=b"")
with urllib.request.urlopen(request, timeout=10) as response:
    if response.status != 204:
        raise RuntimeError("Heartbeat rejected")
