"""Time one HTTPS call to the egress proxy, phase by phase: TCP connect, TLS handshake, request.

What an FDE can measure from inside the customer's network without touching their code:
`make knock` runs it in a throwaway container on the same network as otp-service.
"""
import socket
import ssl
import sys
import time

host, port = "egress-proxy", 8443
body = b'{"to":"+919800000000","text":"probe","reason":"probe"}'
for _ in range(int(sys.argv[1]) if len(sys.argv) > 1 else 5):
    t0 = time.perf_counter()
    raw = socket.create_connection((host, port))
    t1 = time.perf_counter()
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE  # the proxy's CA isn't installed in the lab
    tls = ctx.wrap_socket(raw, server_hostname=host)
    t2 = time.perf_counter()
    tls.sendall(b"POST /v1/messages HTTP/1.1\r\nhost: %s\r\ncontent-type: application/json\r\n"
                b"content-length: %d\r\n\r\n%s" % (host.encode(), len(body), body))
    tls.recv(4096)
    t3 = time.perf_counter()
    tls.close()
    print(f"connect {1000 * (t1 - t0):6.1f} ms | TLS handshake {1000 * (t2 - t1):6.0f} ms | request {1000 * (t3 - t2):5.1f} ms")
