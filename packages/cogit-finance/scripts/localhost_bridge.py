"""Forward a Compose-published port to Runtime's loopback-only dev listener.

Runtime deliberately rejects a non-loopback bind in development mode. Compose
publishes this bridge on the host's 127.0.0.1 only; the bridge runs inside the
server container and forwards bytes to Runtime at 127.0.0.1:8080.
"""

from __future__ import annotations

import asyncio

RUNTIME_HOST = "127.0.0.1"
RUNTIME_PORT = 8080
BRIDGE_HOST = "0.0.0.0"  # noqa: S104 - Docker publishes only host 127.0.0.1.
BRIDGE_PORT = 8081


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while data := await reader.read(65536):
        writer.write(data)
        await writer.drain()
    if writer.can_write_eof():
        writer.write_eof()


async def _handle(
    client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter
) -> None:
    try:
        runtime_reader, runtime_writer = await asyncio.open_connection(
            RUNTIME_HOST, RUNTIME_PORT
        )
    except OSError:
        client_writer.close()
        await client_writer.wait_closed()
        return

    try:
        await asyncio.gather(
            _pipe(client_reader, runtime_writer),
            _pipe(runtime_reader, client_writer),
        )
    finally:
        runtime_writer.close()
        client_writer.close()
        await asyncio.gather(
            runtime_writer.wait_closed(),
            client_writer.wait_closed(),
            return_exceptions=True,
        )


async def _serve() -> None:
    server = await asyncio.start_server(_handle, BRIDGE_HOST, BRIDGE_PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(_serve())
