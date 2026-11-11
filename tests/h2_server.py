"""A minimal HTTP/2 server for the tests.

httpx only speaks HTTP/2 over TLS, because the protocol is chosen with ALPN.
This server offers nothing but h2, answers every request through a handler and
counts the TCP connections and the streams it serves - which is what the pool
tests assert on.
"""

import socket
import ssl
import subprocess
import threading
from pathlib import Path

import h2.config
import h2.connection
import h2.events
import h2.exceptions


def self_signed_certificate(directory: Path) -> tuple[str, str]:
    """Write a certificate for 127.0.0.1 to directory, using the openssl CLI."""
    cert, key = directory / "cert.pem", directory / "key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    return str(cert), str(key)


class H2Server:
    """TLS server that only negotiates h2 and answers handler(path)."""

    def __init__(self, certfile: str, keyfile: str, handler):
        self.handler = handler
        self.connections = 0
        self.streams = 0
        self._context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._context.load_cert_chain(certfile, keyfile)
        self._context.set_alpn_protocols(["h2"])
        self._socket = socket.socket()
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen(16)
        self._socket.settimeout(0.2)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._accept, daemon=True)

    @property
    def port(self) -> int:
        return self._socket.getsockname()[1]

    @property
    def base_url(self) -> str:
        return f"https://127.0.0.1:{self.port}"

    def __enter__(self) -> "H2Server":
        self._thread.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self._stop.set()
        self._socket.close()
        self._thread.join(timeout=5)

    def _accept(self) -> None:
        while not self._stop.is_set():
            try:
                raw, _ = self._socket.accept()
            except TimeoutError:
                continue
            except OSError:
                return
            self.connections += 1
            threading.Thread(target=self._serve, args=(raw,), daemon=True).start()

    def _serve(self, raw: socket.socket) -> None:
        try:
            connection = self._context.wrap_socket(raw, server_side=True)
        except (ssl.SSLError, OSError):
            raw.close()
            return
        if connection.selected_alpn_protocol() != "h2":
            connection.close()
            return
        h2conn = h2.connection.H2Connection(config=h2.config.H2Configuration(client_side=False))
        h2conn.initiate_connection()
        connection.sendall(h2conn.data_to_send())
        try:
            while True:
                data = connection.recv(65535)
                if not data:
                    return
                for event in h2conn.receive_data(data):
                    if isinstance(event, h2.events.RequestReceived):
                        self.streams += 1
                        self._respond(h2conn, event.stream_id, event.headers)
                connection.sendall(h2conn.data_to_send())
        except (ssl.SSLError, OSError, h2.exceptions.ProtocolError):
            pass
        finally:
            connection.close()

    def _respond(self, h2conn, stream_id: int, headers: list[tuple[bytes, bytes]]) -> None:
        path = dict(headers).get(b":path", b"/").decode()
        status, content_type, body = self.handler(path)
        response = [
            (":status", str(status)),
            ("content-type", content_type),
            ("cache-control", "public, max-age=3600"),
        ]
        if body:
            response.append(("content-length", str(len(body))))
        h2conn.send_headers(stream_id, response)
        h2conn.send_data(stream_id, body, end_stream=True)
