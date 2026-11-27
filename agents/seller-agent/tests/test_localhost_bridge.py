"""The local Compose bridge must preserve full-duplex TCP half-closes."""

from __future__ import annotations

import asyncio
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

_BRIDGE = Path(__file__).resolve().parents[1] / "scripts" / "localhost_bridge.py"
_SPEC = spec_from_file_location("template_localhost_bridge", _BRIDGE)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("Could not load the local Compose bridge")
localhost_bridge = module_from_spec(_SPEC)
_SPEC.loader.exec_module(localhost_bridge)


@pytest.mark.asyncio
async def test_client_half_close_still_receives_backend_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"

    async def backend(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await reader.read()
        writer.write(response)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    backend_server = await asyncio.start_server(backend, "127.0.0.1", 0)
    backend_socket = backend_server.sockets[0]
    monkeypatch.setattr(
        localhost_bridge, "RUNTIME_PORT", backend_socket.getsockname()[1]
    )
    bridge_server = await asyncio.start_server(localhost_bridge._handle, "127.0.0.1", 0)
    bridge_socket = bridge_server.sockets[0]
    client_reader, client_writer = await asyncio.open_connection(
        "127.0.0.1", bridge_socket.getsockname()[1]
    )
    try:
        client_writer.write(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await client_writer.drain()
        client_writer.write_eof()
        assert await asyncio.wait_for(client_reader.read(), timeout=5) == response
    finally:
        client_writer.close()
        await client_writer.wait_closed()
        bridge_server.close()
        backend_server.close()
        await asyncio.gather(bridge_server.wait_closed(), backend_server.wait_closed())
