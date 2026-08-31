"""Entry point: start the Prometheus HTTP server and register the XB6 collector."""
from __future__ import annotations

import logging
import time

from prometheus_client import REGISTRY

from .collector import XB6Collector
from .config import load_config
from .server import start_server


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = load_config()

    REGISTRY.register(
        XB6Collector(config.gateway_base_url, config.gateway_username, config.gateway_password)
    )
    start_server(config.exporter_bind, config.exporter_port)
    logging.getLogger(__name__).info(
        "xb6-exporter listening on %s:%s, scraping %s",
        config.exporter_bind,
        config.exporter_port,
        config.gateway_base_url,
    )

    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
