from pathlib import Path
from unittest.mock import patch

from xb6_exporter.client import LoginError
from xb6_exporter.collector import XB6Collector

FIXTURES = Path(__file__).parent / "fixtures"

PAGES = {
    "network_setup.jst": (FIXTURES / "network_setup.html").read_text(),
    "hardware.jst": (FIXTURES / "hardware.html").read_text(),
    "software.jst": (FIXTURES / "software.html").read_text(),
    "wan_network.jst": (FIXTURES / "wan_network.html").read_text(),
}


class FakeXB6Client:
    """Stands in for XB6Client: serves fixture HTML instead of hitting the network."""

    instances: list["FakeXB6Client"] = []

    def __init__(self, base_url, username, password):
        self.logged_in = False
        self.logged_out = False
        FakeXB6Client.instances.append(self)

    def get(self, path):
        return PAGES[path]

    def __enter__(self):
        self.logged_in = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.logged_out = True
        return False


class FailingLoginClient:
    def __init__(self, base_url, username, password):
        pass

    def __enter__(self):
        raise LoginError("simulated login failure")

    def __exit__(self, exc_type, exc, tb):
        return False


def _metric_families_by_name(families):
    return {f.name: f for f in families}


def test_collect_success_reports_up_and_metrics():
    FakeXB6Client.instances = []
    with patch("xb6_exporter.collector.XB6Client", FakeXB6Client):
        collector = XB6Collector("http://gateway.example", "admin", "secret")
        families = list(collector.collect())

    assert FakeXB6Client.instances[0].logged_in is True
    assert FakeXB6Client.instances[0].logged_out is True

    by_name = _metric_families_by_name(families)
    assert by_name["xb6_up"].samples[0].value == 1
    assert "xb6_scrape_duration_seconds" in by_name

    ds_freq = by_name["xb6_downstream_frequency_hz"]
    ch28_sample = next(s for s in ds_freq.samples if s.labels["channel_id"] == "28")
    assert ch28_sample.value == 543_000_000.0

    hw_info = by_name["xb6_hardware_info"]
    assert hw_info.samples[0].labels["model"] == "CGM4140COM"

    wan_up = by_name["xb6_wan_up"]
    assert wan_up.samples[0].value == 1


def test_collect_login_failure_reports_down_without_raising():
    with patch("xb6_exporter.collector.XB6Client", FailingLoginClient):
        collector = XB6Collector("http://gateway.example", "admin", "wrong-password")
        families = list(collector.collect())

    by_name = _metric_families_by_name(families)
    assert by_name["xb6_up"].samples[0].value == 0
    assert "xb6_scrape_duration_seconds" in by_name
    # only the up/duration metrics are emitted on failure
    assert set(by_name) == {"xb6_up", "xb6_scrape_duration_seconds"}
