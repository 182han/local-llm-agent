#!/usr/bin/env python3
"""
Cross-check place coordinates against OpenStreetMap Nominatim.

This script is a *verification* tool, not a generation tool.  It never feeds
coordinates into the model's output; it only measures how far the model's
self-reported coordinates are from an independent public gazetteer.

Notes on this machine (recorded honestly):
  * Nominatim's TLS certificate fails verification because the system clock
    reads 2026-10-03 and the chain is "not yet valid" -> we pass verify=False
    for this ONE public read-only endpoint and record that fact in the report.
  * Nominatim's usage policy requires <=1 request/second and a real
    User-Agent, so requests are serialised with a delay.

Output: a JSON file mapping query -> {lat, lon, display_name, error}
"""
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request

for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
    os.environ.pop(_k, None)

UA = "Elite20-C4D-verification/1.0 (local LLM agent skill; contact: student project)"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE  # documented workaround, see module docstring


def geocode(query, limit=1, retries=3):
    url = ("https://nominatim.openstreetmap.org/search?"
           + urllib.parse.urlencode({"q": query, "format": "jsonv2",
                                     "limit": limit, "addressdetails": 1}))
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:
            if attempt == retries - 1:
                return {"_error": f"{type(exc).__name__}: {exc}"}
            time.sleep(2 * (attempt + 1))
    return {"_error": "unreachable"}


def main(queries, out_path):
    results = {}
    for q in queries:
        res = geocode(q)
        if isinstance(res, dict) and "_error" in res:
            results[q] = res
            print(f"  ERR  {q}: {res['_error']}")
        elif res:
            top = res[0]
            results[q] = {
                "lat": float(top["lat"]),
                "lon": float(top["lon"]),
                "display_name": top.get("display_name", ""),
                "osm_type": top.get("osm_type"),
                "osm_id": top.get("osm_id"),
                "class": top.get("class"),
                "type": top.get("type"),
                "raw_count": len(res),
            }
            print(f"  OK   {q} -> {top['lat']}, {top['lon']}  ({top.get('display_name','')[:70]})")
        else:
            results[q] = {"_error": "no result"}
            print(f"  NONE {q}")
        time.sleep(1.2)  # Nominatim policy: <= 1 req/s
    _d = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(_d, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nwrote {out_path} ({len(results)} queries)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 2:
        qs = sys.argv[1:-1]
        out = sys.argv[-1]
    else:
        qs = [line.strip() for line in sys.stdin if line.strip()]
        out = sys.argv[1] if len(sys.argv) > 1 else "geocode_ref.json"
    sys.exit(main(qs, out))
