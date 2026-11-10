import os

import pytest
import serial

from fprime_gds.common.communication.adapters.uart import SerialAdapter

TIMEOUT = 0.050


@pytest.fixture
def pty():
    """A pseudo-terminal's leader fd and follower device, so pyserial runs its real POSIX code."""
    if not hasattr(os, "openpty"):
        pytest.skip("needs a POSIX pseudo-terminal")
    leader, follower = os.openpty()
    yield leader, os.ttyname(follower)
    os.close(leader)
    os.close(follower)


@pytest.fixture
def adapter(pty):
    adapter = SerialAdapter(pty[1], 115200, True)
    assert adapter.open()
    yield adapter
    adapter.close()


@pytest.fixture
def reconfigurations(adapter, monkeypatch):
    """The timeout of each port reconfiguration made after the adapter opened."""
    calls = []
    original = serial.Serial._reconfigure_port

    def counting_reconfigure(self, *args, **kwargs):
        calls.append(self.timeout)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(serial.Serial, "_reconfigure_port", counting_reconfigure)
    return calls


def test_read_returns_data(adapter, pty):
    """Test reading bytes written to the other end of the port."""
    os.write(pty[0], b"\xde\xad\xbe\xef")
    data = b""
    for _ in range(20):
        data += adapter.read(TIMEOUT)
        if len(data) >= 4:
            break
    assert data == b"\xde\xad\xbe\xef"


def test_read_does_not_reconfigure_port_for_unchanged_timeout(adapter, reconfigurations):
    """
    Test that repeated reads with the same timeout reconfigure the port once. On macOS at high bauds each
    reconfiguration re-sends the baud rate to the driver, which can drop received bytes.
    """
    for _ in range(10):
        assert adapter.read(TIMEOUT) == b""
    assert reconfigurations == [TIMEOUT]


def test_read_applies_changed_timeout(adapter, reconfigurations):
    """Test that a read with a different timeout still applies it."""
    adapter.read(TIMEOUT)
    adapter.read(TIMEOUT)
    adapter.read(TIMEOUT * 2)
    adapter.read(TIMEOUT * 2)
    assert adapter.serial.timeout == TIMEOUT * 2
    assert reconfigurations == [TIMEOUT, TIMEOUT * 2]


def test_reopened_port_gets_timeout(adapter, reconfigurations):
    """Test that the timeout is applied again after the port is reopened."""
    adapter.read(TIMEOUT)
    assert adapter.open()
    reconfigurations.clear()
    adapter.read(TIMEOUT)
    assert adapter.serial.timeout == TIMEOUT
    assert reconfigurations == [TIMEOUT]
