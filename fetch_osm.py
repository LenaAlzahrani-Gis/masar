"""يجلب طبقات OSM للسعودية على مربعات صغيرة ويحفظها في data/city.gpkg

الاستخدام (من مجلد المشروع، والبيئة .venv مفعّلة):
    python fetch_osm.py --list
    python fetch_osm.py police civil_defense
    python fetch_osm.py parks schools mosques
    python fetch_osm.py haramain tourism airports train_stations railways fuel malls
    python fetch_osm.py supermarkets groceries restaurants   (ثقيلة، بالليل)

إذا انقطع التنفيذ، شغّليه مرة ثانية: المربعات المنجزة محفوظة في مجلد cache
ولا تُحمَّل من جديد.
"""
import json
import sys
import time
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import LineString, Point, box
from shapely.prepared import prep

GPKG = Path("data/city.gpkg")
CACHE = Path("cache")

# اسم الطبقة -> شروط الوسوم. القاعدة:
#   - قائمة من (مفتاح، قيمة): كلها لازم تتحقق مع بعض
#   - القيمة "a|b|c": أي واحدة منها
#   - القيمة "*": الوسم موجود بأي قيمة
#   - المفتاح الذي يبدأ بـ ! : الوسم غير موجود
#   - قائمة من القوائم: أي مجموعة منها تكفي
LAYERS = {
    "police": [("amenity", "police")],
    "civil_defense": [("amenity", "fire_station")],
    "parks": [("leisure", "park")],
    "schools": [("amenity", "school")],
    "mosques": [("amenity", "place_of_worship"), ("religion", "muslim")],
    "pharmacies": [("amenity", "pharmacy")],
    "doctors": [("amenity", "doctors")],
    # الجديدة
    "tourism": [
        [("tourism", "attraction|museum|viewpoint|theme_park|zoo|aquarium|gallery")],
        [("historic", "archaeological_site|castle|fort|monument|ruins")],
    ],
    "malls": [("shop", "mall|department_store")],
    "restaurants": [("amenity", "restaurant")],
    "supermarkets": [("shop", "supermarket|hypermarket")],
    "groceries": [("shop", "convenience|grocery")],
    "fuel": [("amenity", "fuel")],
    "banks": [("amenity", "bank")],
    "train_stations": [("railway", "station|halt")],
    "airports": [("aeroway", "aerodrome"), ("iata", "*")],
    "railways": [("railway", "rail|light_rail|subway"), ("!service", "*")],
}

# طبقات خطوط (تُحفظ كخطوط وليس نقاط)
LINE_LAYERS = {"railways"}

# طبقات ثابتة بدون إنترنت: (الاسم بالعربي، بالإنجليزي، خط العرض، خط الطول)
FIXED = {
    "haramain": [
        ("المسجد الحرام", "Masjid al-Haram", 21.4225, 39.8262),
        ("المسجد النبوي", "Al-Masjid an-Nabawi", 24.4672, 39.6111),
    ],
}

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
TILE = 4.0       # حجم المربع بالدرجات
MIN_TILE = 0.25  # أصغر مربع نصل له عند التقسيم
HEADERS = {"User-Agent": "gis-agent-portfolio/1.0"}


def _clause(k, v):
    if k.startswith("!"):
        return f'[!"{k[1:]}"]'
    if v == "*":
        return f'["{k}"]'
    if "|" in v:
        return f'["{k}"~"^({v})$"]'
    return f'["{k}"="{v}"]'


def _sets(filters):
    return filters if filters and isinstance(filters[0], list) else [filters]


def build_query(filters, bbox, geom=False):
    s, w, n, e = bbox
    body = "".join(
        "nwr" + "".join(_clause(k, v) for k, v in fs) + f"({s},{w},{n},{e});"
        for fs in _sets(filters))
    out = "out geom tags;" if geom else "out center tags;"
    return f"[out:json][timeout:120];({body});{out}"


def run_query(query):
    """يجرّب الخوادم بالتناوب مع انتظار متزايد. يرجع قائمة العناصر أو يرمي خطأ."""
    last = None
    for attempt in range(3):
        for url in ENDPOINTS:
            try:
                r = requests.post(url, data={"data": query}, headers=HEADERS, timeout=150)
                if r.status_code == 200:
                    data = r.json()
                    if "runtime error" in data.get("remark", ""):
                        last = f"{url}: {data['remark']}"
                        continue
                    return data["elements"]
                last = f"{url}: HTTP {r.status_code}"
                if r.status_code == 429:
                    time.sleep(20)
            except (requests.RequestException, ValueError) as ex:
                last = f"{url}: {ex}"
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(last)


def fetch_tile(layer, filters, bbox, failed, geom=False):
    """يجلب مربعاً واحداً. إذا فشل يقسمه أربعة أجزاء ويعيد المحاولة."""
    key = CACHE / layer / ("_".join(f"{v:.3f}" for v in bbox) + ".json")
    if key.exists():
        return json.loads(key.read_text(encoding="utf-8"))
    try:
        elements = run_query(build_query(filters, bbox, geom))
        key.parent.mkdir(parents=True, exist_ok=True)
        key.write_text(json.dumps(elements), encoding="utf-8")
        return elements
    except RuntimeError as ex:
        s, w, n, e = bbox
        if (n - s) / 2 < MIN_TILE:
            failed.append(bbox)
            print(f"   فشل مربع {bbox}: {ex}")
            return []
        ms, mw = (s + n) / 2, (w + e) / 2
        parts = [(s, w, ms, mw), (s, mw, ms, e), (ms, w, n, mw), (ms, mw, n, e)]
        print(f"   تقسيم مربع {tuple(round(v, 2) for v in bbox)} بعد الفشل")
        out = []
        for p in parts:
            out += fetch_tile(layer, filters, p, failed, geom)
        return out


def make_tiles(regions):
    """مربعات شبكية تغطي السعودية فقط (نتجاهل المربعات خارج حدود المناطق)."""
    union = prep(regions.unary_union)
    w, s, e, n = regions.total_bounds
    tiles = []
    y = s
    while y < n:
        x = w
        while x < e:
            b = (round(y, 4), round(x, 4), round(min(y + TILE, n), 4), round(min(x + TILE, e), 4))
            if union.intersects(box(b[1], b[0], b[3], b[2])):
                tiles.append(b)
            x += TILE
        y += TILE
    return tiles


def to_points(elements):
    rows, seen = [], set()
    for el in elements:
        uid = (el["type"], el["id"])
        if uid in seen:
            continue
        seen.add(uid)
        if el["type"] == "node":
            lat, lon = el.get("lat"), el.get("lon")
        else:
            c = el.get("center") or {}
            lat, lon = c.get("lat"), c.get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        rows.append({
            "osm_id": f"{el['type'][0]}{el['id']}",
            "name": tags.get("name"),
            "name:ar": tags.get("name:ar"),
            "name:en": tags.get("name:en"),
            "kind": (tags.get("tourism") or tags.get("historic") or tags.get("railway")
                     or tags.get("aeroway")),
            "description": tags.get("description:ar") or tags.get("description"),
            "geometry": Point(lon, lat),
        })
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def to_lines(elements):
    rows, seen = [], set()
    for el in elements:
        if el.get("type") != "way":
            continue
        uid = el["id"]
        pts = el.get("geometry") or []
        if uid in seen or len(pts) < 2:
            continue
        seen.add(uid)
        tags = el.get("tags", {})
        rows.append({
            "osm_id": f"w{uid}",
            "name": tags.get("name"),
            "name:ar": tags.get("name:ar"),
            "name:en": tags.get("name:en"),
            "geometry": LineString([(p["lon"], p["lat"]) for p in pts]),
        })
    return gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")


def build_fixed(layer):
    rows = [{"name": ar, "name:ar": ar, "name:en": en, "kind": layer, "description": None,
             "geometry": Point(lon, lat)}
            for ar, en, lat, lon in FIXED[layer]]
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.to_file(GPKG, layer=layer, driver="GPKG")
    print(f"تم حفظ {layer}: {len(gdf)} نقطة")


def build_layer(layer, regions):
    if layer in FIXED:
        return build_fixed(layer)
    is_line = layer in LINE_LAYERS
    filters = LAYERS[layer]
    tiles = make_tiles(regions)
    print(f"\n== {layer}: {len(tiles)} مربع ==")
    failed, elements = [], []
    for i, bbox in enumerate(tiles, 1):
        print(f"[{i}/{len(tiles)}] {bbox}", end="\r")
        elements += fetch_tile(layer, filters, bbox, failed, is_line)
        time.sleep(1)  # لطف بالخادم
    print()

    gdf = to_lines(elements) if is_line else to_points(elements)
    if gdf.empty:
        print(f"ما وصلت أي نتائج لـ {layer}، ما حفظت شي.")
        return
    # نبقي النقاط داخل حدود السعودية (مربعات الشبكة تلمس دول الجوار)
    gdf = gpd.sjoin(gdf, regions[["geometry"]],
                    predicate="intersects" if is_line else "within", how="inner")
    gdf = gdf.drop(columns="index_right").drop_duplicates("osm_id")
    cols = ["name", "name:ar", "name:en", "geometry"]
    if not is_line:
        cols = ["name", "name:ar", "name:en", "kind", "description", "geometry"]
    gdf = gdf[cols].reset_index(drop=True)

    gdf.to_file(GPKG, layer=layer, driver="GPKG")  # يستبدل هذي الطبقة فقط
    print(f"تم حفظ {layer}: {len(gdf)} {'مقطع' if is_line else 'نقطة'}")
    if failed:
        print(f"تنبيه: {len(failed)} مربع صغير فشل، فالعدد قد يكون ناقصاً. أعيدي التشغيل لمحاولة ثانية.")


def main():
    args = sys.argv[1:]
    if not args or args == ["--list"]:
        print("الطبقات المتاحة:", ", ".join(list(LAYERS) + list(FIXED)))
        return
    allowed = list(LAYERS) + list(FIXED)
    unknown = [a for a in args if a not in allowed]
    if unknown:
        sys.exit(f"طبقة غير معروفة: {unknown}. الطبقات: {allowed}")
    regions = gpd.read_file(GPKG, layer="regions")
    for layer in args:
        build_layer(layer, regions)


if __name__ == "__main__":
    main()