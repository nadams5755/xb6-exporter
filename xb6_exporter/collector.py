"""Custom Prometheus collector: logs into the XB6 gateway, scrapes, logs out, per scrape."""
from __future__ import annotations

import logging
import time

from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector

from . import parser
from .client import XB6Client

logger = logging.getLogger(__name__)


class XB6Collector(Collector):
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.username = username
        self.password = password

    def collect(self):
        start = time.monotonic()
        up = GaugeMetricFamily("xb6_up", "Whether the last scrape of the XB6 gateway succeeded")
        duration = GaugeMetricFamily(
            "xb6_scrape_duration_seconds", "Time spent logging into and scraping the XB6 gateway"
        )

        try:
            metrics = self._scrape()
        except Exception:
            logger.exception("XB6 scrape failed")
            up.add_metric([], 0)
            duration.add_metric([], time.monotonic() - start)
            yield up
            yield duration
            return

        up.add_metric([], 1)
        duration.add_metric([], time.monotonic() - start)
        yield up
        yield duration
        yield from metrics

    def _scrape(self) -> list:
        with XB6Client(self.base_url, self.username, self.password) as client:
            network_setup_html = client.get("network_setup.jst")
            hardware_html = client.get("hardware.jst")
            software_html = client.get("software.jst")
            wan_html = client.get("wan_network.jst")

        network_setup = parser.parse_network_setup(network_setup_html)
        hardware = parser.parse_hardware(hardware_html)
        software = parser.parse_software(software_html)
        wan = parser.parse_wan(wan_html)

        return self._build_metrics(network_setup, hardware, software, wan)

    @staticmethod
    def _build_metrics(ns, hardware, software, wan) -> list:
        nan = float("nan")

        ds_freq = GaugeMetricFamily(
            "xb6_downstream_frequency_hz", "Downstream channel center frequency", labels=["channel_id"]
        )
        ds_power = GaugeMetricFamily(
            "xb6_downstream_power_dbmv", "Downstream channel power level", labels=["channel_id"]
        )
        ds_snr = GaugeMetricFamily(
            "xb6_downstream_snr_db", "Downstream channel signal-to-noise ratio", labels=["channel_id"]
        )
        ds_locked = GaugeMetricFamily(
            "xb6_downstream_locked", "Whether the downstream channel is locked (1) or not (0)", labels=["channel_id"]
        )
        ds_info = GaugeMetricFamily(
            "xb6_downstream_channel_info", "Downstream channel modulation", labels=["channel_id", "modulation"]
        )
        for ch in ns.downstream:
            ds_freq.add_metric([ch.channel_id], ch.frequency_hz if ch.frequency_hz is not None else nan)
            ds_power.add_metric([ch.channel_id], ch.power_dbmv if ch.power_dbmv is not None else nan)
            ds_snr.add_metric([ch.channel_id], ch.snr_db if ch.snr_db is not None else nan)
            ds_locked.add_metric([ch.channel_id], 1 if ch.locked else 0)
            ds_info.add_metric([ch.channel_id, ch.modulation], 1)

        us_freq = GaugeMetricFamily(
            "xb6_upstream_frequency_hz", "Upstream channel center frequency", labels=["channel_id"]
        )
        us_power = GaugeMetricFamily(
            "xb6_upstream_power_dbmv", "Upstream channel power level", labels=["channel_id"]
        )
        us_symbol_rate = GaugeMetricFamily(
            "xb6_upstream_symbol_rate",
            "Upstream channel symbol rate, as reported by the gateway",
            labels=["channel_id"],
        )
        us_locked = GaugeMetricFamily(
            "xb6_upstream_locked", "Whether the upstream channel is locked (1) or not (0)", labels=["channel_id"]
        )
        us_info = GaugeMetricFamily(
            "xb6_upstream_channel_info",
            "Upstream channel modulation and channel type",
            labels=["channel_id", "modulation", "channel_type"],
        )
        for ch in ns.upstream:
            us_freq.add_metric([ch.channel_id], ch.frequency_hz if ch.frequency_hz is not None else nan)
            us_power.add_metric([ch.channel_id], ch.power_dbmv if ch.power_dbmv is not None else nan)
            us_symbol_rate.add_metric([ch.channel_id], ch.symbol_rate if ch.symbol_rate is not None else nan)
            us_locked.add_metric([ch.channel_id], 1 if ch.locked else 0)
            us_info.add_metric([ch.channel_id, ch.modulation, ch.channel_type], 1)

        cw_unerrored = GaugeMetricFamily(
            "xb6_downstream_codewords_unerrored_total",
            "Cumulative unerrored codewords received on a downstream channel",
            labels=["channel_id"],
        )
        cw_correctable = GaugeMetricFamily(
            "xb6_downstream_codewords_correctable_total",
            "Cumulative correctable codeword errors on a downstream channel",
            labels=["channel_id"],
        )
        cw_uncorrectable = GaugeMetricFamily(
            "xb6_downstream_codewords_uncorrectable_total",
            "Cumulative uncorrectable codeword errors on a downstream channel",
            labels=["channel_id"],
        )
        for cw in ns.codewords:
            cw_unerrored.add_metric([cw.channel_id], cw.unerrored if cw.unerrored is not None else nan)
            cw_correctable.add_metric([cw.channel_id], cw.correctable if cw.correctable is not None else nan)
            cw_uncorrectable.add_metric(
                [cw.channel_id], cw.uncorrectable if cw.uncorrectable is not None else nan
            )

        wan_up = GaugeMetricFamily("xb6_wan_up", "Whether the WAN/DOCSIS connection is up (1) or down (0)")
        wan_up.add_metric([], 1 if (ns.registration_complete and wan.ip4) else 0)

        wan_info = GaugeMetricFamily(
            "xb6_wan_info", "WAN connection details", labels=["ip4", "ip6", "operational_mode"]
        )
        wan_info.add_metric([wan.ip4, wan.ip6, wan.operational_mode], 1)

        hardware_info = GaugeMetricFamily(
            "xb6_hardware_info",
            "Gateway hardware identity",
            labels=["model", "vendor", "hardware_revision", "serial_number"],
        )
        hardware_info.add_metric(
            [hardware.model, hardware.vendor, hardware.hardware_revision, hardware.serial_number], 1
        )

        software_info = GaugeMetricFamily(
            "xb6_software_info",
            "Gateway software identity",
            labels=["docsis_software_version", "image_name", "packet_cable_version"],
        )
        software_info.add_metric(
            [software.docsis_software_version, software.image_name, software.packet_cable_version], 1
        )

        return [
            ds_freq,
            ds_power,
            ds_snr,
            ds_locked,
            ds_info,
            us_freq,
            us_power,
            us_symbol_rate,
            us_locked,
            us_info,
            cw_unerrored,
            cw_correctable,
            cw_uncorrectable,
            wan_up,
            wan_info,
            hardware_info,
            software_info,
        ]
