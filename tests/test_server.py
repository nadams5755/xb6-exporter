import socket
import threading

from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector, CollectorRegistry

from xb6_exporter.server import _make_locking_app, _resolve_bind_address


class SlowCollector(Collector):
    """A collector whose collect() blocks until told to proceed, to simulate an
    in-flight gateway login/scrape/logout cycle."""

    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()

    def collect(self):
        self.entered.set()
        self.release.wait(timeout=5)
        metric = GaugeMetricFamily("test_metric", "test")
        metric.add_metric([], 1)
        yield metric


def _call(app, path="/metrics", method="GET"):
    environ = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": ""}
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = headers

    body = b"".join(app(environ, start_response))
    return captured["status"], body


def test_concurrent_scrape_returns_429():
    registry = CollectorRegistry()
    collector = SlowCollector()
    registry.register(collector)
    app = _make_locking_app(registry)

    results = {}

    def first_request():
        results["first"] = _call(app)

    thread = threading.Thread(target=first_request)
    thread.start()
    assert collector.entered.wait(timeout=2), "first request never reached collect()"

    status, body = _call(app)
    assert status.startswith("429")
    assert b"already in progress" in body

    collector.release.set()
    thread.join(timeout=5)
    assert results["first"][0].startswith("200")


def test_resolve_bind_address_dual_stack_and_ipv4():
    family, addr = _resolve_bind_address("::", 0)
    assert family == socket.AF_INET6
    assert addr == "::"

    family, addr = _resolve_bind_address("127.0.0.1", 0)
    assert family == socket.AF_INET
    assert addr == "127.0.0.1"
