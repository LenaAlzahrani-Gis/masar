"""مسار: الطقس والصلاة والقبلة ودرجة الوصول وتحليل الفجوات (بدون واجهة)."""
import math
from datetime import datetime, timedelta, timezone

import numpy as np
import requests

KSA = timezone(timedelta(hours=3))          # المملكة بدون توقيت صيفي
KAABA = (21.4225, 39.8262)
HEADERS = {'User-Agent': 'masar-portfolio/1.0'}


def now_ksa():
    return datetime.now(KSA)


# ---------------------------------------------------------------- الجغرافيا
def haversine_matrix(lat1, lon1, lat2, lon2):
    """مسافات بالكيلومتر بين مجموعتين من النقاط: الشكل (len(1), len(2))."""
    p1 = np.radians(np.asarray(lat1, dtype=float))[:, None]
    p2 = np.radians(np.asarray(lat2, dtype=float))[None, :]
    dl = np.radians(np.asarray(lon2, dtype=float))[None, :] - np.radians(np.asarray(lon1, dtype=float))[:, None]
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def haversine_1(lat, lon, lats, lons):
    return haversine_matrix([lat], [lon], lats, lons)[0]


_COORDS = {}


def coords(key, gdf):
    """(خطوط العرض، خطوط الطول) لنقاط الطبقة، مع تخزين مؤقت."""
    k = (key, len(gdf))
    if k not in _COORDS:
        g = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
        pts = g.geometry.representative_point()
        _COORDS[k] = (pts.y.to_numpy(), pts.x.to_numpy())
    return _COORDS[k]


# ---------------------------------------------------------------- القبلة
def qibla_bearing(lat, lon):
    p1, p2 = math.radians(lat), math.radians(KAABA[0])
    dl = math.radians(KAABA[1] - lon)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass_ar(deg):
    names = ['شمال', 'شمال شرق', 'شرق', 'جنوب شرق', 'جنوب', 'جنوب غرب', 'غرب', 'شمال غرب']
    return names[int((deg + 22.5) // 45) % 8]


# ---------------------------------------------------------------- الطقس
def wmo(code):
    if code == 0:
        return 'صافٍ', '☀️'
    if code in (1, 2):
        return 'غائم جزئياً', '⛅'
    if code == 3:
        return 'غائم', '☁️'
    if code in (45, 48):
        return 'ضباب', '🌫️'
    if code in (51, 53, 55, 56, 57):
        return 'رذاذ', '🌦️'
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return 'أمطار', '🌧️'
    if code in (71, 73, 75, 77, 85, 86):
        return 'ثلوج', '❄️'
    if code in (95, 96, 99):
        return 'عاصفة رعدية', '⛈️'
    return 'غير معروف', '🌡️'


def fetch_weather(lat, lon):
    """يرمي استثناء عند الفشل (حتى لا يُخزَّن الفشل مؤقتاً)."""
    r = requests.get(
        'https://api.open-meteo.com/v1/forecast', headers=HEADERS, timeout=8,
        params={'latitude': lat, 'longitude': lon, 'timezone': 'auto', 'forecast_days': 1,
                'current': 'temperature_2m,relative_humidity_2m,apparent_temperature,is_day,weather_code,wind_speed_10m',
                'daily': 'temperature_2m_max,temperature_2m_min,uv_index_max'})
    r.raise_for_status()
    j = r.json()
    c, d = j['current'], j['daily']
    desc, icon = wmo(int(c['weather_code']))
    return {'temp': c['temperature_2m'], 'feels': c['apparent_temperature'],
            'humidity': c['relative_humidity_2m'], 'wind': c['wind_speed_10m'],
            'code': int(c['weather_code']), 'is_day': bool(c['is_day']),
            'desc': desc, 'icon': icon,
            'tmax': d['temperature_2m_max'][0], 'tmin': d['temperature_2m_min'][0],
            'uv': d['uv_index_max'][0]}


def advice(w):
    """اقتراح عام حسب الجو: {'mood','text','keys'} (قاعدة بسيطة وليست توصية رسمية)."""
    feels, wind, code = w['feels'], w['wind'], w['code']
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99):
        out = {'mood': 'rain', 'keys': ['malls', 'supermarkets'],
               'text': 'احتمال أمطار الآن. تجنّب الأودية والمنخفضات وتنقّل بحذر.'}
    elif feels >= 40:
        out = {'mood': 'hot', 'keys': ['malls', 'supermarkets', 'restaurants'],
               'text': 'الجو حار جداً. الأفضل الأماكن المكيّفة وتجنّب النشاط الخارجي وقت الظهيرة.'}
    elif feels >= 34:
        out = {'mood': 'warm', 'keys': ['malls', 'parks'],
               'text': 'الجو دافئ. اختر الأماكن المظلّلة واشرب الماء بانتظام.'}
    elif wind >= 40:
        out = {'mood': 'wind', 'keys': ['malls'],
               'text': 'الرياح نشطة وقد يكثر الغبار. يُفضّل تقليل الوقت خارج المبنى.'}
    elif feels >= 16:
        out = {'mood': 'mild', 'keys': ['parks', 'tourism'],
               'text': 'الجو لطيف ومناسب للحدائق والأماكن المفتوحة.'}
    else:
        out = {'mood': 'cool', 'keys': ['restaurants', 'malls'],
               'text': 'الجو بارد نسبياً. خذ ملابس مناسبة.'}
    if w.get('uv') is not None and w['uv'] >= 8 and out['mood'] not in ('rain',):
        out['text'] += ' الأشعة فوق البنفسجية عالية اليوم.'
    return out


ACCENTS = {'hot': '#c2410c', 'warm': '#b45309', 'rain': '#1d4ed8', 'wind': '#6d28d9', 'cool': '#0369a1'}


# ---------------------------------------------------------------- الصلاة
PRAYERS = [('Fajr', 'الفجر'), ('Dhuhr', 'الظهر'), ('Asr', 'العصر'), ('Maghrib', 'المغرب'), ('Isha', 'العشاء')]


def fetch_prayer(lat, lon, day):
    """day بصيغة DD-MM-YYYY. التقويم: أم القرى (method=4). يرمي استثناء عند الفشل."""
    r = requests.get(f'https://api.aladhan.com/v1/timings/{day}', headers=HEADERS, timeout=8,
                     params={'latitude': lat, 'longitude': lon, 'method': 4})
    r.raise_for_status()
    t = r.json()['data']['timings']
    return {k: t[k][:5] for k, _ in PRAYERS}


def next_prayer(today, tomorrow, now):
    """(الاسم، الوقت، المتبقي بالدقائق) للصلاة القادمة."""
    for key, name in PRAYERS:
        h, m = map(int, today[key].split(':'))
        t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if t > now:
            return name, today[key], int((t - now).total_seconds() // 60)
    src = tomorrow or today
    h, m = map(int, src['Fajr'].split(':'))
    t = (now + timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)
    return 'الفجر', src['Fajr'], int((t - now).total_seconds() // 60)


def remaining_text(minutes):
    h, m = divmod(max(minutes, 0), 60)
    if h and m:
        return f'بعد {h} س و{m} د'
    if h:
        return f'بعد {h} س'
    return f'بعد {m} د'


# ---------------------------------------------------------------- درجة الوصول
# (الطبقة، المسافة المثالية كم، الوزن، نصف قطر العد كم)
ACCESS_SPEC = [
    ('hospitals', 10, 3, 10), ('clinics', 5, 1, 5), ('pharmacies', 3, 2, 3),
    ('schools', 2, 2, 3), ('mosques', 1, 2, 2), ('parks', 3, 1, 3),
    ('supermarkets', 3, 1, 3), ('groceries', 1.5, 1, 2), ('fuel', 5, 1, 5),
    ('police', 10, 1, 10), ('civil_defense', 10, 1, 10),
]


def _name_of(row):
    for c in ('name:ar', 'name', 'name:en'):
        v = row.get(c)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def access_report(layers, loc):
    """يحسب درجة 0-100 من الطبقات المتوفرة. يرجع None إذا لا توجد طبقات صالحة."""
    rows, total_w, acc = [], 0, 0.0
    for key, ideal, w, radius in ACCESS_SPEC:
        gdf = layers.get(key)
        if gdf is None or len(gdf) == 0:
            continue
        lats, lons = coords(key, gdf)
        d = haversine_1(loc[0], loc[1], lats, lons)
        i = int(d.argmin())
        near = float(d[i])
        sub = 1.0 if near <= ideal else max(0.0, 1 - (near - ideal) / (2 * ideal))
        total_w += w
        acc += w * sub
        rows.append({'key': key, 'nearest_km': near, 'count': int((d <= radius).sum()),
                     'radius': radius, 'ideal': ideal, 'sub': sub,
                     'name': _name_of(gdf.iloc[i]),
                     'lat': float(lats[i]), 'lon': float(lons[i])})
    if not rows:
        return None
    score = round(100 * acc / total_w)
    label = ('ممتاز' if score >= 80 else 'جيد' if score >= 60 else 'متوسط' if score >= 40 else 'ضعيف')
    return {'score': score, 'label': label, 'rows': rows}


# ---------------------------------------------------------------- فجوات الخدمات
GAP_LEGEND = [(10, '#16a34a', 'أقل من 10 كم'), (25, '#84cc16', '10 إلى 25 كم'),
              (50, '#facc15', '25 إلى 50 كم'), (100, '#fb923c', '50 إلى 100 كم'),
              (float('inf'), '#dc2626', 'أكثر من 100 كم')]


def gap_color(km):
    for lim, col, _ in GAP_LEGEND:
        if km <= lim:
            return col
    return GAP_LEGEND[-1][1]


def gap_grid(key, gdf, regions, step=0.3):
    """شبكة تغطي المملكة. كل خلية: لون حسب المسافة لأقرب مرفق. يرجع (features, مصفوفة المسافات)."""
    from shapely.geometry import Point
    from shapely.prepared import prep

    lats, lons = coords(key, gdf)
    geom = regions.geometry
    union = geom.union_all() if hasattr(geom, 'union_all') else geom.unary_union
    union = prep(union)
    w, s, e, n = regions.total_bounds
    cells, lat = [], s + step / 2
    while lat < n:
        lon = w + step / 2
        while lon < e:
            if union.contains(Point(lon, lat)):
                cells.append((lat, lon))
            lon += step
        lat += step
    if not cells:
        return [], np.array([])
    cl = np.array(cells)
    dmin = np.empty(len(cl))
    for i in range(0, len(cl), 150):
        c = cl[i:i + 150]
        dmin[i:i + 150] = haversine_matrix(c[:, 0], c[:, 1], lats, lons).min(axis=1)
    h = step / 2
    feats = []
    for (la, lo), d in zip(cells, dmin):
        feats.append({'type': 'Feature',
                      'properties': {'km': round(float(d), 1), 'color': gap_color(float(d))},
                      'geometry': {'type': 'Polygon', 'coordinates': [[
                          [lo - h, la - h], [lo + h, la - h], [lo + h, la + h],
                          [lo - h, la + h], [lo - h, la - h]]]}})
    return feats, dmin


def gov_table(key, gdf, gov):
    """جدول المحافظات: عدد المرافق داخلها وبعد أقرب مرفق عن مركز المحافظة."""
    import geopandas as gpd
    import pandas as pd

    lats, lons = coords(key, gdf)
    cols = [c for c in ('name:ar', 'name', 'name:en') if c in gov.columns]
    names = []
    for i in range(len(gov)):
        row = {c: gov.iloc[i][c] for c in cols}
        names.append(_name_of(row) or f'محافظة {i + 1}')
    cp = gov.geometry.representative_point()
    dist = haversine_matrix(cp.y.to_numpy(), cp.x.to_numpy(), lats, lons).min(axis=1)
    pts = gpd.GeoDataFrame(geometry=gdf.geometry.representative_point(), crs=gdf.crs)
    j = gpd.sjoin(pts, gov[['geometry']].reset_index(drop=True), predicate='within', how='inner')
    counts = j['index_right'].value_counts()
    df = pd.DataFrame({
        'المحافظة': names,
        'عدد المرافق داخلها': [int(counts.get(i, 0)) for i in range(len(gov))],
        'أقرب مرفق من مركز المحافظة (كم)': np.round(dist, 1)})
    return df.sort_values('أقرب مرفق من مركز المحافظة (كم)', ascending=False).reset_index(drop=True)