"""CLI: ingest text files or URLs into the vector store."""
from __future__ import annotations

import argparse
import asyncio
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .pipeline import vector_store


class UnsafeUrlError(ValueError):
    """Raised when a URL targets a private/loopback/metadata address (SSRF guard)."""


def _is_safe_url(url: str) -> bool:
    """F-027: block SSRF. Reject non-http(s) schemes and any host that resolves to a
    private, loopback, link-local, or cloud-metadata address (169.254.169.254)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = parsed.hostname
    if not host:
        return False
    try:
        # Resolve ALL addresses (defeats DNS-rebinding to a single safe record)
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr.split("%")[0])  # strip scope id
        except ValueError:
            return False
        if (
            ip.is_private or ip.is_loopback or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified
        ):
            return False
        if str(ip) == "169.254.169.254":  # explicit: cloud metadata endpoint
            return False
    return True


def ingest_file(path: str, source_label: str | None = None) -> int:
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    label = source_label or Path(path).name
    n = vector_store.ingest(text, metadata={"source": label})
    print(f"Ingested {n} chunks from {label}")
    return n


async def ingest_url(url: str) -> int:
    if not _is_safe_url(url):
        raise UnsafeUrlError(f"Refusing to fetch unsafe/internal URL: {url}")
    # Disable redirects — a public URL could 30x-redirect to an internal address.
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        text = resp.text
    n = vector_store.ingest(text, metadata={"source": url})
    print(f"Ingested {n} chunks from {url}")
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest documents into F.A.B.L.E. RAG store")
    parser.add_argument("sources", nargs="+", help="File paths or URLs to ingest")
    parser.add_argument("--label", help="Override source label for all inputs")
    args = parser.parse_args()

    total = 0
    for src in args.sources:
        if src.startswith("http://") or src.startswith("https://"):
            total += asyncio.run(ingest_url(src))
        else:
            total += ingest_file(src, args.label)
    print(f"\nTotal chunks ingested: {total}")


if __name__ == "__main__":
    main()
