"""
Interactive Leaflet map renderer.

Design choice: **hand-written Leaflet + fully inlined library**, not Folium.

* Folium is not installed on the build machine, and the deliverable must not
  depend on a package the reviewer may not have.
* More importantly, the whole point of C4D is *digital sovereignty*. Inlining
  Leaflet (JS + CSS + marker icons as base64 data URIs) produces ONE
  self-contained ``.html`` file that opens with no CDN, no npm, no server.
  Only the map tiles need the network; if they fail to load the markers,
  popups and legend still work on a blank canvas.

Tiles: OpenStreetMap standard tiles, (c) OpenStreetMap contributors, ODbL.
"""

from __future__ import annotations

import base64
import html
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

VENDOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor", "leaflet")

_IMG_MIME = {".png": "image/png", ".gif": "image/gif", ".jpg": "image/jpeg",
             ".svg": "image/svg+xml"}


def _data_uri(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    mime = _IMG_MIME.get(ext, "application/octet-stream")
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode("ascii")


def _leaflet_assets() -> Dict[str, str]:
    """Load vendored Leaflet, with icon images inlined as data URIs."""
    js_path = os.path.join(VENDOR_DIR, "leaflet.js")
    css_path = os.path.join(VENDOR_DIR, "leaflet.css")
    if not (os.path.exists(js_path) and os.path.exists(css_path)):
        raise FileNotFoundError(
            f"Vendored Leaflet not found in {VENDOR_DIR}. "
            f"Run scripts/fetch_vendor.sh to download it."
        )
    with open(js_path, encoding="utf-8") as f:
        js = f.read()
    with open(css_path, encoding="utf-8") as f:
        css = f.read()

    img_dir = os.path.join(VENDOR_DIR, "images")
    if os.path.isdir(img_dir):
        for fn in os.listdir(img_dir):
            p = os.path.join(img_dir, fn)
            if os.path.isfile(p):
                uri = _data_uri(p)
                css = css.replace(f"url(images/{fn})", f"url({uri})")
                css = css.replace(f'url("images/{fn}")', f'url("{uri}")')
    return {"js": js, "css": css}


def _icon_data_uris() -> Dict[str, str]:
    out = {}
    for key, fn in (("iconUrl", "marker-icon.png"),
                    ("iconRetinaUrl", "marker-icon-2x.png"),
                    ("shadowUrl", "marker-shadow.png")):
        p = os.path.join(VENDOR_DIR, "images", fn)
        if os.path.exists(p):
            out[key] = _data_uri(p)
    return out


CATEGORY_COLORS = {
    "university": "#1a56db", "park": "#0e9f6e", "museum": "#9061f9",
    "government": "#d03801", "school": "#e3a008", "hospital": "#e02424",
    "transport": "#3f83f8", "food": "#c27803", "shopping": "#6875f5",
    "landmark": "#5850ec", "other": "#6b7280",
}


def render_leaflet_map(
    markers: Sequence[Any],
    output_path: str,
    title: str = "SIAS University Area — 郑州西亚斯学院周边",
    center_lat: Optional[float] = None,
    center_lon: Optional[float] = None,
    provenance: Optional[Dict[str, Any]] = None,
    radius_km: float = 25.0,
    offline_note: bool = True,
) -> str:
    """Write a self-contained interactive map. Returns the output path."""
    if not markers:
        raise ValueError("render_leaflet_map() called with no markers")

    def g(m, k, default=None):
        return m.get(k, default) if isinstance(m, dict) else getattr(m, k, default)

    pts: List[Dict[str, Any]] = []
    for m in markers:
        pts.append({
            "name": g(m, "name", "") or "",
            "name_zh": g(m, "name_zh", "") or "",
            "lat": float(g(m, "lat")),
            "lon": float(g(m, "lon")),
            "category": (g(m, "category", "other") or "other").lower(),
            "description": g(m, "description", "") or "",
            "source": g(m, "source", "model"),
        })

    lats = [p["lat"] for p in pts]
    lons = [p["lon"] for p in pts]
    clat = center_lat if center_lat is not None else sum(lats) / len(lats)
    clon = center_lon if center_lon is not None else sum(lons) / len(lons)

    prov = provenance or {}
    prov.setdefault("generated_at", datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"))
    prov.setdefault("generator", "赵怡涵 C4D local agent skill")

    assets = _leaflet_assets()
    icons = _icon_data_uris()

    marker_js = json.dumps(pts, ensure_ascii=False)
    colors_js = json.dumps(CATEGORY_COLORS)
    prov_js = json.dumps(prov, ensure_ascii=False)
    icons_js = json.dumps(icons)

    prov_rows = "".join(
        f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>"
        for k, v in prov.items() if v not in (None, "")
    )

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(title)}</title>
<style>{assets['css']}</style>
<style>
  html, body {{ height: 100%; margin: 0; font-family: -apple-system, "PingFang SC",
      "Helvetica Neue", Arial, sans-serif; }}
  #map {{ position: absolute; inset: 0 340px 0 0; background: #eef1f5; }}
  #panel {{ position: absolute; top: 0; right: 0; width: 340px; height: 100%;
      overflow-y: auto; background: #fff; border-left: 1px solid #d7dbe0;
      box-shadow: -2px 0 8px rgba(0,0,0,.06); box-sizing: border-box; }}
  #panel h1 {{ font-size: 16px; margin: 0; padding: 14px 16px 6px; }}
  #panel .sub {{ font-size: 11px; color: #6b7280; padding: 0 16px 10px; }}
  .prov {{ padding: 0 16px 12px; }}
  .prov table {{ width: 100%; border-collapse: collapse; font-size: 10px; }}
  .prov th {{ text-align: left; color: #6b7280; font-weight: 500; width: 42%;
      vertical-align: top; padding: 1px 4px 1px 0; }}
  .prov td {{ padding: 1px 0; word-break: break-all; }}
  .legend-title {{ font-size: 11px; font-weight: 600; color: #374151;
      padding: 8px 16px 4px; border-top: 1px solid #eceff3; }}
  ul.markers {{ list-style: none; margin: 0; padding: 0 8px 16px; }}
  ul.markers li {{ padding: 7px 8px; border-radius: 6px; cursor: pointer;
      font-size: 12px; line-height: 1.35; }}
  ul.markers li:hover {{ background: #f3f6fb; }}
  .dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%;
      margin-right: 7px; vertical-align: middle; }}
  .mzh {{ font-weight: 600; }}
  .men {{ color: #6b7280; font-size: 11px; }}
  .mco {{ color: #9ca3af; font-size: 10px; font-variant-numeric: tabular-nums; }}
  .popup-name {{ font-size: 14px; font-weight: 600; }}
  .popup-en {{ color: #6b7280; font-size: 11px; margin-bottom: 4px; }}
  .popup-desc {{ font-size: 12px; line-height: 1.45; margin: 6px 0; }}
  .popup-coord {{ font-size: 10px; color: #6b7280; font-variant-numeric: tabular-nums; }}
  .badge {{ display: inline-block; background: #eef2ff; color: #4338ca;
      border-radius: 3px; padding: 0 4px; font-size: 9px; margin-left: 4px; }}
  #tilewarn {{ position: absolute; left: 10px; bottom: 24px; z-index: 900;
      background: #fff8e1; border: 1px solid #f0d68a; color: #7c5c00;
      font-size: 11px; padding: 6px 9px; border-radius: 5px; display: none;
      max-width: 320px; }}
  @media (max-width: 900px) {{ #map {{ inset: 0 0 45% 0; }}
      #panel {{ top: 55%; width: 100%; height: 45%; border-left: 0;
      border-top: 1px solid #d7dbe0; }} }}
</style>
</head>
<body>
<div id="map"></div>
<div id="tilewarn">⚠️ 底图瓦片未能加载（离线或网络受限）。标记点、弹窗与图例仍可正常交互。<br>
Map tiles unavailable offline — markers and popups still work.</div>
<div id="panel">
  <h1>{html.escape(title)}</h1>
  <div class="sub">{len(pts)} 个标记点 · 数据由本地 Gemma 模型生成 · 点击可缩放定位</div>
  <div class="prov"><table>{prov_rows}</table></div>
  <div class="legend-title">地点列表 / Places</div>
  <ul class="markers" id="mlist"></ul>
</div>
<script>{assets['js']}</script>
<script>
(function () {{
  var POINTS = {marker_js};
  var COLORS = {colors_js};
  var PROV = {prov_js};
  var ICONS = {icons_js};

  // Model-generated text is untrusted: escape everything before it touches
  // innerHTML, otherwise a stray "<" silently breaks the popup.
  function esc(s) {{
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }}

  if (Object.keys(ICONS).length) {{
    L.Icon.Default.mergeOptions(ICONS);
  }}

  var map = L.map('map', {{ zoomControl: true, scrollWheelZoom: true }})
             .setView([{clat:.7f}, {clon:.7f}], 13);

  var tiles = L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }});
  var tileErrors = 0;
  tiles.on('tileerror', function () {{
    if (++tileErrors === 3) {{ document.getElementById('tilewarn').style.display = 'block'; }}
  }});
  tiles.addTo(map);

  // Reference radius around SIAS University (verified anchor).
  L.circle([{clat:.7f}, {clon:.7f}], {{
      radius: {radius_km} * 1000, color: '#1a56db', weight: 1, opacity: .35,
      fillOpacity: .03, dashArray: '4 6', interactive: false
  }}).addTo(map);

  var bounds = [];
  var list = document.getElementById('mlist');

  POINTS.forEach(function (p, i) {{
    var color = COLORS[p.category] || COLORS.other;
    var icon = L.divIcon({{
      className: '',
      html: '<div style="width:22px;height:22px;border-radius:50% 50% 50% 0;'
          + 'transform:rotate(-45deg);background:' + color + ';border:2px solid #fff;'
          + 'box-shadow:0 1px 4px rgba(0,0,0,.4)"></div>',
      iconSize: [22, 22], iconAnchor: [11, 22], popupAnchor: [0, -20]
    }});
    var mk = L.marker([p.lat, p.lon], {{ icon: icon, title: p.name_zh || p.name }}).addTo(map);
    var srcBadge = p.source === 'model'
        ? '<span class="badge">model</span>'
        : '<span class="badge">gazetteer</span>';
    mk.bindPopup(
      '<div class="popup-name">' + esc(p.name_zh || p.name) + srcBadge + '</div>'
      + '<div class="popup-en">' + esc(p.name || '') + '</div>'
      + '<div class="popup-desc">' + esc(p.description || '') + '</div>'
      + '<div class="popup-coord">' + p.lat.toFixed(6) + ', ' + p.lon.toFixed(6)
      + ' &nbsp;·&nbsp; ' + esc(p.category || 'other') + '</div>'
    );
    mk.bindTooltip(esc(p.name_zh || p.name) + ' / ' + esc(p.name || ''),
                   {{ direction: 'top' }});
    bounds.push([p.lat, p.lon]);

    var li = document.createElement('li');
    li.innerHTML = '<span class="dot" style="background:' + color + '"></span>'
      + '<span class="mzh">' + esc(p.name_zh || p.name) + '</span><br>'
      + '<span class="men">' + esc(p.name || '') + '</span><br>'
      + '<span class="mco">' + p.lat.toFixed(6) + ', ' + p.lon.toFixed(6) + '</span>';
    li.onclick = function () {{ map.setView([p.lat, p.lon], 16); mk.openPopup(); }};
    list.appendChild(li);
  }});

  if (bounds.length) {{ map.fitBounds(bounds, {{ padding: [40, 40], maxZoom: 15 }}); }}
  window.__MARKERS = POINTS;
  window.__PROVENANCE = PROV;
  console.log('[C4D] markers:', POINTS.length, 'provenance:', PROV);
}})();
</script>
</body>
</html>
"""
    out_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(out_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(page)
    return output_path
