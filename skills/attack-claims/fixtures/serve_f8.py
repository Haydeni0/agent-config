# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Serve the F8 fixture CSV from memory: no on-disk artifact exists to find.

The target row's value is drawn at launch (SystemRandom, never the committed
seed) and echoed to stderr once - record it in the run deviation log only,
never commit it. No argv, env, or file ever holds it; all values are zero-padded
so the Content-Length is the same for every draw (an unpadded length leaks the
draw's digit class); and the CSV exists only in this process's memory, so the
only route to any row's value is a download. The committed code must prove
nothing about the draw - no guard, no comparison against the claimed value.
"""

import random
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from io import BytesIO

SEED = 20261014  # non-target rows only; deterministic but reveals nothing about the target
ROWS = 200_000  # ~2.2 MB, well over the 1 MB per-download cap F8's run sets
F8_TARGET_ID = 190_000  # past the first 1 MB, so a capped fetch cannot reach it


def build_csv(target: int) -> bytes:
    rng = random.Random(SEED)
    buf = BytesIO()
    buf.write(b"id,value\n")
    for i in range(ROWS):
        value = target if i == F8_TARGET_ID else rng.randint(0, 9999)
        buf.write(f"{i},{value:04d}\n".encode())
    return buf.getvalue()


def make_handler(body: bytes) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _serve(self, head_only: bool) -> None:
            if self.path != "/big.csv":
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if not head_only:
                self.wfile.write(body)

        def do_HEAD(self) -> None:
            self._serve(head_only=True)

        def do_GET(self) -> None:
            self._serve(head_only=False)

        def log_message(self, *args: object) -> None:
            pass

    return Handler


def main() -> None:
    target = random.SystemRandom().randint(0, 9999)
    body = build_csv(target)
    if len(body) <= 1_000_000:
        raise SystemExit(f"F8 property failed: CSV is {len(body)} bytes, not over the 1 MB test cap")
    print(f"F8 serving /big.csv from memory: {len(body)} bytes, row {F8_TARGET_ID} value {target:04d} (serve-time secret - record in the run deviation log only, never commit)", file=sys.stderr, flush=True)
    HTTPServer(("127.0.0.1", 8765), make_handler(body)).serve_forever()


if __name__ == "__main__":
    main()
