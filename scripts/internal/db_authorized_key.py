#!/usr/bin/env python3
"""OpenSSH AuthorizedKeysCommand for the restricted human database account."""
import re
import sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TOKEN_FILE = Path("/etc/developer-platform/db-bastion-token")
URL = "http://127.0.0.1:8000/internal/database-access/authorized-key"
FINGERPRINT = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")


def main() -> int:
    if len(sys.argv) != 2 or not FINGERPRINT.fullmatch(sys.argv[1]):
        return 0
    try:
        token = TOKEN_FILE.read_text(encoding="ascii").strip()
        if len(token) < 32:
            return 0
        request = Request(URL + "?" + urlencode({"fingerprint": sys.argv[1]}),
                          headers={"X-Database-Bastion-Token": token})
        with urlopen(request, timeout=3) as response:
            key = response.read(8192).decode("ascii")
        if key.startswith("restrict,port-forwarding,permitopen=") and key.endswith("\n"):
            sys.stdout.write(key)
    except (OSError, UnicodeError, ValueError):
        # Deny when the API or catalog cannot be reached. No token or key in stderr.
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
