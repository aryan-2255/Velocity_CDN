#!/usr/bin/env python3
"""Uploads a handful of small demo files to Origin so /fetch has something to
serve on a fresh stack. Run after `docker compose up`:

    python3 scripts/seed_demo.py
    python3 scripts/seed_demo.py --origin http://localhost:8000 --count 20
"""

import argparse
import random
import sys
import urllib.error
import urllib.request
import uuid

BOUNDARY = "----velocitycacheboundary"


def build_multipart(field_name: str, filename: str, content_type: str, data: bytes) -> tuple[bytes, str]:
    parts = [
        f"--{BOUNDARY}\r\n".encode(),
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        data,
        f"\r\n--{BOUNDARY}--\r\n".encode(),
    ]
    return b"".join(parts), f"multipart/form-data; boundary={BOUNDARY}"


def upload(origin: str, key: str, data: bytes) -> None:
    body, content_type = build_multipart("upload", key, "text/plain", data)
    req = urllib.request.Request(
        f"{origin}/files?key={key}",
        data=body,
        method="POST",
        headers={"Content-Type": content_type},
    )
    with urllib.request.urlopen(req) as resp:
        print(f"  uploaded {key} ({len(data)} bytes) -> {resp.status}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default="http://localhost:8000")
    parser.add_argument("--count", type=int, default=10, help="number of demo files to create")
    args = parser.parse_args()

    print(f"Seeding {args.count} demo files into {args.origin} ...")
    for i in range(args.count):
        key = f"demo/file-{i:02d}.txt"
        # Small, distinct payloads (10KB-ish) — big enough to see eviction with a low
        # CACHE_MAX_BYTES override, small enough to keep S3 egress trivial.
        data = f"Velocity CDN demo file #{i} — {uuid.uuid4()}\n".encode() * 400
        try:
            upload(args.origin, key, data)
        except urllib.error.URLError as exc:
            print(f"  FAILED {key}: {exc}", file=sys.stderr)
            return 1

    print("Done. Try:")
    print(f'  curl "http://localhost:8080/fetch/demo/file-00.txt?region=mumbai" -o /dev/null -sw "%{{http_code}} %header{{x-cache-result}}\\n"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
