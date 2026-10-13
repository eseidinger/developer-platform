"""Non-secret TOML profiles and keyring session binding."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import tomllib
from urllib.parse import urlsplit

from platformdirs import user_config_path

from .config import ConfigurationError


def validate_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError("Use an HTTP(S) URL without credentials, query, or fragment.")
    return value.rstrip("/")


@dataclass(frozen=True)
class Profile:
    api_url: str
    issuer: str
    client_id: str = "platform-cli"
    ca_bundle: str | None = None
    project: str | None = None
    output: str = "table"

    def __post_init__(self):
        validate_url(self.api_url)
        validate_url(self.issuer)
        if not self.client_id or self.output not in {"json", "table", "plain"}:
            raise ConfigurationError("Invalid profile client ID or output format.")


class ProfileStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or Path(os.environ.get("DEVPLAT_CONFIG_DIR") or user_config_path("devplat"))
        self.path = self.directory / "profiles.toml"

    def read(self) -> dict:
        try:
            return tomllib.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"profiles": {}}
        except (OSError, ValueError):
            raise ConfigurationError("Unable to read CLI profiles.") from None

    def selected(self, name: str | None = None) -> tuple[str | None, Profile | None]:
        data = self.read()
        selected = name or data.get("active")
        if not selected:
            return None, None
        try:
            return selected, Profile(**data["profiles"][selected])
        except (KeyError, TypeError):
            raise ConfigurationError("The selected profile does not exist or is invalid.") from None

    def write(self, data: dict) -> None:
        lines = []
        if data.get("active"):
            lines.append("active = " + json.dumps(data["active"]))
        for name, profile in sorted(data.get("profiles", {}).items()):
            lines.append("\n[profiles." + json.dumps(name) + "]")
            lines.extend(key + " = " + json.dumps(value) for key, value in profile.items() if value is not None)
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory, delete=False) as stream:
                temporary = Path(stream.name)
                os.chmod(temporary, 0o600)
                stream.write("\n".join(lines) + "\n")
            temporary.replace(self.path)
        except OSError:
            raise ConfigurationError("Unable to save CLI profiles.") from None

    def create(self, name: str, profile: Profile) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", name):
            raise ConfigurationError("Use a profile name containing letters, digits, hyphens, or underscores.")
        data = self.read()
        if name in data.get("profiles", {}):
            raise ConfigurationError("Profile already exists; delete it explicitly before recreating it.")
        data.setdefault("profiles", {})[name] = asdict(profile)
        data.setdefault("active", name)
        self.write(data)

    def use(self, name: str) -> None:
        self.selected(name)
        data = self.read()
        data["active"] = name
        self.write(data)

    def delete(self, name: str) -> None:
        self.selected(name)
        data = self.read()
        del data["profiles"][name]
        if data.get("active") == name:
            data.pop("active")
        self.write(data)


class SessionStore:
    """Persist refresh tokens only through a usable OS credential backend."""

    def __init__(self, name: str, profile: Profile):
        binding = json.dumps([name, profile.api_url, profile.issuer, profile.client_id])
        self.service = "devplat:" + hashlib.sha256(binding.encode()).hexdigest()
        self.name, self.profile = name, profile

    def backend(self):
        import keyring

        backend = keyring.get_keyring()
        module = type(backend).__module__
        if backend.priority <= 0 or "keyrings.alt" in module or "plaintext" in module.lower():
            raise ConfigurationError("A secure OS keyring is required for human login; use an externally supplied access token on headless hosts.")
        return keyring

    def get(self) -> dict | None:
        try:
            raw = self.backend().get_password(self.service, self.name)
            if raw is None:
                return None
            session = json.loads(raw)
            if session.get("issuer") != self.profile.issuer or session.get("client_id") != self.profile.client_id or not session.get("subject") or not session.get("refresh_token"):
                raise ConfigurationError("Stored session binding is invalid; sign in again.")
            return session
        except ConfigurationError:
            raise
        except Exception:
            raise ConfigurationError("Unable to read the OS keyring session.") from None

    def set(self, subject: str, refresh_token: str) -> None:
        session = {"issuer": self.profile.issuer, "client_id": self.profile.client_id,
                   "subject": subject, "refresh_token": refresh_token}
        try:
            self.backend().set_password(self.service, self.name, json.dumps(session))
        except ConfigurationError:
            raise
        except Exception:
            raise ConfigurationError("Unable to save the OS keyring session.") from None

    def delete(self) -> None:
        try:
            backend = self.backend()
            if backend.get_password(self.service, self.name) is not None:
                backend.delete_password(self.service, self.name)
        except ConfigurationError:
            raise
        except Exception:
            raise ConfigurationError("Unable to clear the OS keyring session.") from None
