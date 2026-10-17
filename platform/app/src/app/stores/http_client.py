"""Bounded private provider requests. Never follow credential-bearing redirects."""
import json
import ssl
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, HTTPSHandler, build_opener
from .s3 import NoRedirect, StoreError


class PrivateJSON:
    def __init__(self, endpoint, headers, ca_file=None):
        self.endpoint, self.headers = endpoint, headers
        self.opener = build_opener(ProxyHandler({}), NoRedirect(),
            HTTPSHandler(context=ssl.create_default_context(cafile=ca_file)))

    def request(self, method, path, body=None, missing=False):
        data = json.dumps(body, separators=(',', ':')).encode() if body is not None else None
        request = Request(self.endpoint + path, data=data, method=method,
            headers={**self.headers, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=5) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise StoreError('Provider response exceeded its limit')
                return json.loads(raw) if raw else {}
        except HTTPError as error:
            if missing and error.code == 404:
                return None
            # Codes are safe; URLs, bodies and authentication diagnostics are not.
            raise StoreError(f'Provider request failed ({error.code})') from None
