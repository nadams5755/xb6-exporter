"""Exporter configuration: gateway credentials (env vars, falling back to .credentials) plus exporter knobs (env vars)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values

CREDENTIALS_PATH = Path(__file__).resolve().parent.parent / ".credentials"


@dataclass
class Config:
    gateway_base_url: str
    gateway_username: str
    gateway_password: str
    exporter_bind: str
    exporter_port: int


def load_config() -> Config:
    creds = dotenv_values(CREDENTIALS_PATH) if CREDENTIALS_PATH.is_file() else {}
    gwaddr = os.environ.get("GWADDR") or creds.get("GWADDR")
    gwuser = os.environ.get("GWUSER") or creds.get("GWUSER")
    gwpassword = os.environ.get("GWPASSWORD") or creds.get("GWPASSWORD")
    if not gwaddr or not gwuser or not gwpassword:
        raise RuntimeError(
            "missing GWADDR/GWUSER/GWPASSWORD; set them as environment variables "
            f"or in {CREDENTIALS_PATH} (copy .credentials_template to .credentials and fill it in)"
        )

    return Config(
        gateway_base_url=f"http://{gwaddr}",
        gateway_username=gwuser,
        gateway_password=gwpassword,
        exporter_bind=os.environ.get("EXPORTER_BIND", "::"),
        exporter_port=int(os.environ.get("EXPORTER_PORT", "9938")),
    )
