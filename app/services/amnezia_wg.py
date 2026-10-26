from __future__ import annotations

from dataclasses import dataclass
import re


AMNEZIA_WG_ENDPOINTS: dict[str, str] = {
    "FI-2": "103.110.64.30:51820",
    "NL-1": "87.58.216.244:51820",
    "GE-1": "103.27.156.60:51820",
    "FR-1": "188.130.207.6:51820",
    "LV-1": "95.182.85.132:51820",
    "LV-2": "95.182.90.91:51820",
}

_SERVER_ALIASES: dict[str, str] = {
    "fi": "FI-2",
    "fi2": "FI-2",
    "fi-2": "FI-2",
    "finland": "FI-2",
    "finland2": "FI-2",
    "finland-2": "FI-2",
    "nl": "NL-1",
    "nl1": "NL-1",
    "nl-1": "NL-1",
    "netherlands": "NL-1",
    "netherlands1": "NL-1",
    "netherlands-1": "NL-1",
    "ge": "GE-1",
    "ge1": "GE-1",
    "ge-1": "GE-1",
    "de": "GE-1",
    "de1": "GE-1",
    "de-1": "GE-1",
    "germany": "GE-1",
    "germany1": "GE-1",
    "germany-1": "GE-1",
    "fr": "FR-1",
    "fr1": "FR-1",
    "fr-1": "FR-1",
    "france": "FR-1",
    "france1": "FR-1",
    "france-1": "FR-1",
    "lv": "LV-1",
    "lv1": "LV-1",
    "lv-1": "LV-1",
    "latvia": "LV-1",
    "latvia1": "LV-1",
    "latvia-1": "LV-1",
    "lv2": "LV-2",
    "lv-2": "LV-2",
    "latvia2": "LV-2",
    "latvia-2": "LV-2",
}


@dataclass(frozen=True)
class AmneziaConfig:
    available: bool
    text: str | None = None
    endpoint: str | None = None
    server_code: str | None = None


def _normalize_key(value: str | None) -> str:
    if not value:
        return ""
    value = value.casefold().strip()
    value = value.replace("_", "-").replace(" ", "-")
    value = re.sub(r"[^a-z0-9-]+", "", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value


def resolve_amnezia_server_code(*candidates: str | None) -> str | None:
    for candidate in candidates:
        key = _normalize_key(candidate)
        if not key:
            continue
        direct = key.upper()
        if direct in AMNEZIA_WG_ENDPOINTS:
            return direct
        compact = key.replace("-", "")
        if compact.upper() in AMNEZIA_WG_ENDPOINTS:
            return compact.upper()
        alias = _SERVER_ALIASES.get(key) or _SERVER_ALIASES.get(compact)
        if alias:
            return alias
    return None


def build_amnezia_config(config_text: str, server_id: str, server_name: str | None = None, country: str | None = None) -> AmneziaConfig:
    server_code = resolve_amnezia_server_code(server_id, server_name, country)
    if not server_code:
        return AmneziaConfig(available=False)

    endpoint = AMNEZIA_WG_ENDPOINTS[server_code]
    pattern = re.compile(r"(?im)^(Endpoint\s*=\s*).*$")
    amended, count = pattern.subn(rf"\g<1>{endpoint}", config_text, count=1)
    if count == 0:
        amended = config_text.rstrip() + f"\nEndpoint = {endpoint}\n"

    return AmneziaConfig(
        available=True,
        text=amended,
        endpoint=endpoint,
        server_code=server_code,
    )
