"""The /metrics HTTP server: dual-stack (IPv4+IPv6) by default, and returns 429 for a
scrape request that arrives while a previous one is still logged into the gateway."""
from __future__ import annotations

import socket
import threading
from wsgiref.simple_server import WSGIRequestHandler, make_server

from prometheus_client import REGISTRY, make_wsgi_app
from prometheus_client.exposition import ThreadingWSGIServer
from prometheus_client.registry import CollectorRegistry

_TRIGGERS_COLLECT = {"GET", "HEAD"}


class _SilentHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        pass


def _resolve_bind_address(host: str, port: int):
    """Resolve `host` to a socket family + address, e.g. "::" -> (AF_INET6, "::")."""
    family, _, _, _, sockaddr = next(
        iter(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, flags=socket.AI_PASSIVE))
    )
    return family, sockaddr[0]


def _make_locking_app(registry: CollectorRegistry):
    """Wrap the prometheus WSGI app with a non-blocking lock.

    Only one gateway login/scrape/logout cycle can run at a time (the gateway itself
    only supports a single admin session), so a request that arrives mid-scrape gets an
    immediate 429 instead of queueing behind it or racing it for the gateway session.
    """
    metrics_app = make_wsgi_app(registry)
    lock = threading.Lock()

    def app(environ, start_response):
        if environ.get("PATH_INFO") == "/favicon.ico" or environ.get("REQUEST_METHOD") not in _TRIGGERS_COLLECT:
            return metrics_app(environ, start_response)

        if not lock.acquire(blocking=False):
            body = b"a scrape of the XB6 gateway is already in progress, try again shortly\n"
            start_response(
                "429 Too Many Requests",
                [
                    ("Content-Type", "text/plain; charset=utf-8"),
                    ("Content-Length", str(len(body))),
                    ("Retry-After", "5"),
                ],
            )
            return [body]
        try:
            return metrics_app(environ, start_response)
        finally:
            lock.release()

    return app


def start_server(bind: str, port: int, registry: CollectorRegistry = REGISTRY) -> threading.Thread:
    family, addr = _resolve_bind_address(bind, port)

    class _Server(ThreadingWSGIServer):
        address_family = family

    httpd = make_server(addr, port, _make_locking_app(registry), _Server, handler_class=_SilentHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return thread
