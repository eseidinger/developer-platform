"""Resolve public image tags to immutable digests before a revision is accepted."""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_REGISTRIES = "docker.io,ghcr.io,quay.io"
TIMEOUT_SECONDS = 10
MANIFEST_TYPES = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
# Docker Hub serves the registry and its anonymous token service from different hosts.
API_HOSTS = {"docker.io": ("registry-1.docker.io", "auth.docker.io")}


class ImageResolutionError(Exception):
    """`reason` is one of unsupported_registry, not_found, or unavailable."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def allowed_registries() -> set[str]:
    configured = os.environ.get("IMAGE_REGISTRIES", DEFAULT_REGISTRIES)
    return {item.strip().lower() for item in configured.split(",") if item.strip()}


def parse_reference(image: str) -> tuple[str, str, str | None, str | None]:
    """Return registry, repository path, tag and digest for an image reference."""
    name, _, digest = image.partition("@")
    first, _, rest = name.partition("/")
    if rest and ("." in first or ":" in first or first == "localhost"):
        registry, path = first.lower(), rest
    else:
        registry, path = "docker.io", name
    tag = None
    head, _, last = path.rpartition("/")
    if ":" in last:
        last, _, tag = last.partition(":")
        path = f"{head}/{last}" if head else last
    if registry == "docker.io" and "/" not in path:
        path = "library/" + path
    return registry, path, tag or (None if digest else "latest"), digest or None


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _request(url: str, headers: dict[str, str], method: str = "GET") -> tuple[int, dict[str, str], bytes]:
    opener = urllib.request.build_opener(_NoRedirects)
    try:
        with opener.open(urllib.request.Request(url, headers=headers, method=method),
                         timeout=TIMEOUT_SECONDS) as response:
            return response.status, {k.lower(): v for k, v in response.headers.items()}, response.read(65536)
    except urllib.error.HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in exc.headers.items()}, b""
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ImageResolutionError("unavailable") from exc


def _anonymous_token(challenge: str, hosts: tuple[str, ...], path: str) -> str:
    params = dict(re.findall(r'(\w+)="([^"]*)"', challenge))
    realm = urllib.parse.urlsplit(params.get("realm", ""))
    if not challenge.lower().startswith("bearer") or realm.scheme != "https" or realm.hostname not in hosts:
        raise ImageResolutionError("unavailable")
    query = {"scope": f"repository:{path}:pull"}
    if "service" in params:
        query["service"] = params["service"]
    status, _, body = _request(f"{params['realm']}?{urllib.parse.urlencode(query)}", {})
    if status != 200:
        raise ImageResolutionError("unavailable")
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise ImageResolutionError("unavailable") from exc
    token = data.get("token") or data.get("access_token")
    if not isinstance(token, str) or not token:
        raise ImageResolutionError("unavailable")
    return token


def resolve_image(image: str) -> str:
    """Return `<repository>@sha256:<digest>` for the image tag without changing the repository name."""
    registry, path, tag, digest = parse_reference(image)
    if digest:
        if not DIGEST.match(digest):
            raise ImageResolutionError("not_found")
        return image
    if registry not in allowed_registries():
        raise ImageResolutionError("unsupported_registry")
    api_host, token_host = API_HOSTS.get(registry, (registry, registry))
    url = f"https://{api_host}/v2/{urllib.parse.quote(path)}/manifests/{urllib.parse.quote(tag)}"
    headers = {"Accept": MANIFEST_TYPES}
    status, response, _ = _request(url, headers, "HEAD")
    if status == 401:
        token = _anonymous_token(response.get("www-authenticate", ""), (api_host, token_host), path)
        status, response, _ = _request(url, {**headers, "Authorization": "Bearer " + token}, "HEAD")
    if status in (401, 403, 404):
        raise ImageResolutionError("not_found")
    resolved = response.get("docker-content-digest", "")
    if status != 200 or not DIGEST.match(resolved):
        raise ImageResolutionError("unavailable")
    repository = image.partition("@")[0]
    last = repository.rpartition("/")[2]
    if ":" in last:
        repository = repository[:len(repository) - len(last)] + last.partition(":")[0]
    return f"{repository}@{resolved}"
