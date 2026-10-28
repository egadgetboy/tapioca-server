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

    def _check(address):
        host = address[0] if isinstance(address, tuple) else address
        if not isinstance(address, tuple):
            return  # (a Unix socket's path)
        try:
            ip = ipaddress.ip_address(str(host).split("%", 1)[0])
        except ValueError:
            # (A name: only this machine's own may be asked by name. The second round of 1.44.0's audit.)
            if str(host) in ("localhost", "localhost.localdomain"):
                return
            raise LeftTheMachine(f"A security test tried to reach {host} by name: the suite never leaves this machine") from None
        if not ip.is_loopback:
            raise LeftTheMachine(f"A security test tried to reach {host}: the suite never leaves this machine")

    def connect(self, address):
        _check(address)
        return real(self, address)

    real_ex, real_sendto = socket.socket.connect_ex, socket.socket.sendto

    def connect_ex(self, address):
        _check(address)
        return real_ex(self, address)

    def sendto(self, data, *rest):
        # (sendto(data, address) or sendto(data, flags, address): the address is last.)
        _check(rest[-1])
        return real_sendto(self, data, *rest)

    monkeypatch.setattr(socket.socket, "connect", connect)
    # (The security audit of 1.44.0: connect_ex and UDP's sendto went around the guard.)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", sendto)
    real_sendmsg = socket.socket.sendmsg

    def sendmsg(self, buffers, ancdata=(), flags=0, address=None):
        if address is not None:
            _check(address)
            return real_sendmsg(self, buffers, ancdata, flags, address)
        return real_sendmsg(self, buffers, ancdata, flags)

    monkeypatch.setattr(socket.socket, "sendmsg", sendmsg)
