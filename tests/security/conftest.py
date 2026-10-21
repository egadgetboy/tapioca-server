"""The suite's egress guard (DL287, 13.4): no security test reaches the
real network. Any connection to an address that isn't this machine's own
fails the test that made it. (The SSRF checks never rely on this guard to
pass: they assert tapiOca's own decision before it connects.)"""

from __future__ import annotations

import ipaddress
import socket

import pytest


class LeftTheMachine(AssertionError):
    pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    real = socket.socket.connect

    def connect(self, address):
        host = address[0] if isinstance(address, tuple) else address
        try:
            ip = ipaddress.ip_address(str(host).split("%", 1)[0])
        except ValueError:
            ip = None  # (a Unix socket's path)
        if ip is not None and not ip.is_loopback:
            raise LeftTheMachine(f"A security test tried to reach {host}: the suite never leaves this machine")
        return real(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)
