"""The bank's egress proxy (simulated). Every outbound HTTPS call from PayKaro goes through it.

It terminates TLS so the bank can inspect traffic, then forwards plain HTTP to the vendor. The
inspection cost is simulated: HANDSHAKE_DELAY_S is added before the proxy answers the TLS
ClientHello, so the client sees a fast TCP connect and a slow TLS handshake, as with a real
inspecting proxy under load. Connection: close on every response, so every send pays it.
"""
import asyncio
import os
import random
import ssl

import httpx
import trustme

UPSTREAM = os.environ["UPSTREAM_URL"]
DELAY = float(os.environ.get("HANDSHAKE_DELAY_S", "1.7"))
JITTER = float(os.environ.get("HANDSHAKE_JITTER_S", "0.3"))

ca = trustme.CA()
tls = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
ca.issue_cert("egress-proxy").configure_cert(tls)
client = httpx.AsyncClient(timeout=10)


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        await asyncio.sleep(max(0.0, random.gauss(DELAY, JITTER)))  # "inspection"
        await writer.start_tls(tls)
        head = await reader.readuntil(b"\r\n\r\n")
        method, path, _ = head.split(b"\r\n", 1)[0].decode().split(" ", 2)
        headers = dict(
            line.split(": ", 1) for line in head.decode().split("\r\n")[1:] if ": " in line
        )
        length = int(headers.get("content-length", headers.get("Content-Length", "0")))
        body = await reader.readexactly(length) if length else b""
        r = await client.request(method, f"{UPSTREAM}{path}", content=body,
                                 headers={"content-type": headers.get("content-type", "application/json")})
        writer.write(
            f"HTTP/1.1 {r.status_code} {r.reason_phrase}\r\ncontent-type: application/json\r\n"
            f"content-length: {len(r.content)}\r\nconnection: close\r\n\r\n".encode() + r.content
        )
        await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionError, ssl.SSLError, httpx.HTTPError):
        pass
    finally:
        writer.close()


async def main() -> None:
    server = await asyncio.start_server(handle, "0.0.0.0", 8443)
    async with server:
        await server.serve_forever()


asyncio.run(main())
