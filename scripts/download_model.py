#!/usr/bin/env python3
"""
Download a GGUF model from Hugging Face — fast, resumable, checksum-verified.

WHY THIS SCRIPT EXISTS (a real incident, recorded in 赵怡涵_C4D_AI日志.md)
------------------------------------------------------------------------
`ollama pull` returns HTTP 401 on this machine: the registry rejects the
request.  So the model is fetched as a plain GGUF from Hugging Face and turned
into an Ollama model with `ollama create`.  That works, but the first attempt
used a single `curl`, which measured **289 KB/s** — nearly 3 hours for 2.9 GiB.

Benchmarking (scripts/bench_throughput.py) showed the CDN gives a fast initial
burst per TCP connection and then throttles hard:

      8 conns x 8 MB chunks   ->   153 KB/s
     24 conns x 2 MB chunks   ->  3030 KB/s      (~20x)

So this script requests many SMALL byte ranges with high parallelism and
reconnects constantly.  It is also crash-safe: finished chunk offsets are
appended to a journal file, so an interrupted run resumes rather than restarting.

Usage
-----
    python3 scripts/download_model.py                     # default: E2B Q4_K_M
    python3 scripts/download_model.py --list              # show known files
    python3 scripts/download_model.py --repo unsloth/gemma-4-E2B-it-GGUF \
            --file gemma-4-E2B-it-Q8_0.gguf --out /tmp/dl/
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)  # the local system proxy is ~10x slower here

# Known files: repo, filename, bytes, sha256 (from the HF API `?blobs=true`)
KNOWN = {
    "e2b-q4km": ("unsloth/gemma-4-E2B-it-GGUF", "gemma-4-E2B-it-Q4_K_M.gguf",
                 3106738272,
                 "740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8"),
    "e2b-q8": ("unsloth/gemma-4-E2B-it-GGUF", "gemma-4-E2B-it-Q8_0.gguf",
               5048352864,
               "605d3c2647d7c58c1e4b5375ccb5702acf94c2611b4c8d4877812f8fdd32d053"),
    "e4b-q4km": ("unsloth/gemma-4-E4B-it-GGUF", "gemma-4-E4B-it-Q4_K_M.gguf",
                 4977171584,
                 "85a896a047553e842f25297ee5b031d64ff30147d9c4af17b1e4b394cd1fab87"),
}


def hf_metadata(repo: str, filename: str):
    """Ask the HF API for the authoritative size + sha256 of one file."""
    url = f"https://huggingface.co/api/models/{repo}?blobs=true"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.7.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read().decode())
    for s in data.get("siblings", []):
        if s.get("rfilename") == filename:
            lfs = s.get("lfs") or {}
            return int(s.get("size") or 0), lfs.get("sha256")
    return None, None


def download(url: str, out: str, total: int, sha: str,
             conns: int = 24, chunk_mb: int = 2, max_attempts: int = 6) -> int:
    chunk = chunk_mb * 1024 * 1024
    journal = out + ".journal"

    done_offsets = set()
    if os.path.exists(journal) and os.path.exists(out):
        with open(journal) as f:
            for line in f:
                if line.strip().isdigit():
                    done_offsets.add(int(line.strip()))
        print(f"resume: {len(done_offsets)} chunks already on disk")

    fd = os.open(out, os.O_RDWR | os.O_CREAT, 0o644)
    os.ftruncate(fd, total)
    jfd = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)

    offsets = [o for o in range(0, total, chunk) if o not in done_offsets]
    total_chunks = (total + chunk - 1) // chunk
    already = total_chunks - len(offsets)
    lock = threading.Lock()
    state = {"n": already, "bytes": already * chunk, "failed": []}
    t0 = time.time()

    def one(s: int) -> bool:
        e = min(s + chunk, total) - 1
        want = e - s + 1
        for attempt in range(1, max_attempts + 1):
            try:
                req = urllib.request.Request(
                    url, headers={"Range": f"bytes={s}-{e}", "User-Agent": "curl/8.7.1"})
                buf = bytearray()
                with urllib.request.urlopen(req, timeout=45) as r:
                    while len(buf) < want:
                        b = r.read(min(262144, want - len(buf)))
                        if not b:
                            break
                        buf += b
                if len(buf) == want:
                    os.pwrite(fd, bytes(buf), s)
                    os.write(jfd, f"{s}\n".encode())
                    with lock:
                        state["n"] += 1
                        state["bytes"] += want
                        if state["n"] % 50 == 0 or state["n"] == total_chunks:
                            el = max(time.time() - t0, 1e-6)
                            rate = state["bytes"] / 1048576 / el
                            left = (total - state["bytes"]) / 1048576
                            print(f"  {state['n']}/{total_chunks} chunks "
                                  f"{100.0*state['n']/total_chunks:5.1f}%  "
                                  f"{rate:6.2f} MB/s  eta {left/rate/60 if rate else 0:5.1f} min",
                                  flush=True)
                    return True
                time.sleep(1.5 * attempt)
            except Exception:
                time.sleep(1.5 * attempt)
        with lock:
            state["failed"].append(s)
        return False

    try:
        with ThreadPoolExecutor(max_workers=conns) as ex:
            list(ex.map(one, offsets))
    finally:
        os.close(fd)
        os.close(jfd)

    if state["failed"]:
        print(f"INCOMPLETE: {len(state['failed'])} chunks failed — rerun to resume")
        return 2
    size = os.path.getsize(out)
    print(f"\nsize actual={size} expected={total}")
    if size != total:
        print("SIZE MISMATCH")
        return 1
    h = hashlib.sha256()
    with open(out, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    actual = h.hexdigest()
    print(f"sha256 actual  = {actual}")
    print(f"sha256 expected= {sha}")
    if actual == sha:
        print("SHA256 OK")
        try:
            os.remove(journal)
        except OSError:
            pass
        return 0
    print("SHA256 MISMATCH")
    return 3


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preset", default="e2b-q4km", choices=sorted(KNOWN))
    ap.add_argument("--repo", default=None)
    ap.add_argument("--file", default=None)
    ap.add_argument("--out", default="/tmp/dl")
    ap.add_argument("--conns", type=int, default=24)
    ap.add_argument("--chunk-mb", type=int, default=2)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    if args.list:
        print("known files (size, sha256 taken from the Hugging Face API):")
        for k, (repo, fn, size, sha) in KNOWN.items():
            print(f"  {k:10} {repo}/{fn}  {size/2**30:.2f} GiB  {sha[:16]}...")
        return 0

    if args.repo and args.file:
        repo, fn = args.repo, args.file
        size, sha = hf_metadata(repo, fn)
        if not size:
            print(f"FAIL: {repo}/{fn} not found via the HF API", file=sys.stderr)
            return 4
    else:
        repo, fn, size, sha = KNOWN[args.preset]

    os.makedirs(args.out, exist_ok=True)
    dest = os.path.join(args.out, fn)

    if os.path.exists(dest) and os.path.getsize(dest) == size and not os.path.exists(dest + ".journal"):
        h = hashlib.sha256()
        with open(dest, "rb") as f:
            for blk in iter(lambda: f.read(1 << 20), b""):
                h.update(blk)
        if h.hexdigest() == sha:
            print(f"already downloaded and verified: {dest}")
            return 0

    url = f"https://huggingface.co/{repo}/resolve/main/{fn}"
    print(f"repo      : {repo}")
    print(f"file      : {fn}")
    print(f"size      : {size} bytes ({size/2**30:.2f} GiB)")
    print(f"sha256    : {sha}")
    print(f"dest      : {dest}")
    print(f"strategy  : {args.conns} connections x {args.chunk_mb} MB ranges\n")
    return download(url, dest, size, sha, args.conns, args.chunk_mb)


if __name__ == "__main__":
    sys.exit(main())
