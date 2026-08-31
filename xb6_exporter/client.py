"""HTTP client for the XB6 gateway's admin web UI (plain form login, session cookie)."""
from __future__ import annotations

import requests


class LoginError(Exception):
    pass


class XB6Client:
    """Logs into the gateway admin UI, fetches pages, and logs out.

    Use as a context manager so logout() always runs, even if a fetch or the
    caller's parsing raises:

        with XB6Client(base_url, user, password) as client:
            html = client.get("network_setup.jst")
    """

    def __init__(self, base_url: str, username: str, password: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.session = requests.Session()

    def login(self) -> None:
        response = self.session.post(
            f"{self.base_url}/check.jst",
            data={"username": self.username, "password": self.password, "locale": "false"},
            timeout=self.timeout,
            allow_redirects=False,
        )
        if response.status_code != 302 or not self.session.cookies:
            raise LoginError(
                f"login failed: unexpected response {response.status_code} from {self.base_url}/check.jst"
            )

    def get(self, path: str) -> str:
        response = self.session.get(f"{self.base_url}/{path.lstrip('/')}", timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def logout(self) -> None:
        self.session.get(f"{self.base_url}/home_loggedout.jst", timeout=self.timeout)

    def __enter__(self) -> "XB6Client":
        self.login()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            self.logout()
        finally:
            self.session.close()
