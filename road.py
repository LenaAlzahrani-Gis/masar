"""مسار: رحلة البر الآمنة. مسار الطريق + تحليل فجوات الوقود والمستشفيات على امتداده."""
import json
import re

import numpy as np
import requests

import extras

MODEL = 'claude-sonnet-5-5'
OSRM = 'https://router.project-osrm.org/route/v1/driving/'
GEOCODE = 'https://geocoding-api.open-meteo.com/v1/search'

DEFAULT_RANGE = 450          # كم تقطعها السيارة بخزان كامل
RESERVE = 0.8                # نعتمد 80% من المدى فقط (احتياط 20%)
FUEL_CORRIDOR_KM = 3.0       # محطة تُحتسب إذا كانت ضمن 3 كم من الطريق
HOSP_CORRIDOR_KM = 6.0
CLUSTER_KM = 1.5             # محطات متجاورة تُدمج في نقطة واحدة


# ------------------------------------------------------------- فهم الطلب
def parse_request(text):
    """يرجع dict: origin (اسم أو None)، dest، range_km (رقم أو None)."""
    import anthropic

    system = (
        'حوّل وصف رحلة بالسيارة داخل السعودية إلى JSON فقط بدون أي شرح، بالشكل: '
        '{"origin": null, "origin_en": null, "dest": "اسم المدينة", "dest_en": "city name in English", "range_km": null}. '
        'origin هو اسم مدينة البداية إذا ذكرها المستخدم، وإلا null (يعني من موقعه الحالي). '
        'dest هو اسم الوجهة (مدينة أو بلدة) بالعربي. origin_en و dest_en هما نفس الاسمين بالإنجليزية (الاسم الشائع في الخرائط). '
        'range_km هو عدد الكيلومترات التي تقطعها السيارة بخزان كامل إذا ذكرها، وإلا null. '
        'إذا لم تجد وجهة فأرجع {"dest": null}.')
    client = anthropic.Anthropic()
    msg = client.messages.create(model=MODEL, max_tokens=200, system=system,
                                 messages=[{'role': 'user', 'content': text}])
    raw = ''.join(b.text for b in msg.content if getattr(b, 'type', '') == 'text')
    m = re.search(r'\{.*\}', raw, re.S)
    data = json.loads(m.group(0)) if m else {}
    rng = data.get('range_km')
    try:
        rng = float(rng) if rng else None
    except (TypeError, ValueError):
        rng = None
    return {'origin': (data.get('origin') or None), 'origin_en': data.get('origin_en') or None,
            'dest': (data.get('dest') or None), 'dest_en': data.get('dest_en') or None, 'range_km': rng}


NOMINATIM = 'https://nominatim.openstreetmap.org/search'


def _geocode_open_meteo(name, lang='ar'):
    try:
        r = requests.get(GEOCODE, headers=extras.HEADERS, timeout=10,
                         params={'name': name, 'count': 8, 'language': lang, 'format': 'json',
                                 'countryCode': 'SA'})
        r.raise_for_status()
        res = r.json().get('results') or []
    except Exception:
        return None
    if not res:
        return None
    ppl = [x for x in res if str(x.get('feature_code', '')).startswith('PPL')] or res
    best = ppl[0]
    return float(best['latitude']), float(best['longitude']), best.get('name') or name


def _geocode_nominatim(name):
    """بحث OpenStreetMap: تغطيته أوسع للمدن الصغيرة والقرى."""
    try:
        r = requests.get(NOMINATIM, headers=extras.HEADERS, timeout=12,
                         params={'q': name, 'format': 'jsonv2', 'countrycodes': 'sa',
                                 'accept-language': 'ar', 'limit': 6})
        r.raise_for_status()
        res = r.json() or []
    except Exception:
        return None
    if not res:
        return None
    places = [x for x in res if x.get('category') in ('place', 'boundary')] or res
    best = places[0]
    nm = (best.get('name') or str(best.get('display_name', name)).split('،')[0] or name).strip()
    return float(best['lat']), float(best['lon']), nm


def _variants(name):
    """صيغ إملائية شائعة للاسم: همزات وتاء مربوطة وأل التعريف."""
    n = (name or '').strip()
    out = [n]
    alt = n.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    if alt != n:
        out.append(alt)
    for pre in ('مدينة ', 'محافظة ', 'منطقة '):
        if n.startswith(pre):
            out.append(n[len(pre):])
    if n.startswith('ال') and len(n) > 3:
        out.append(n[2:])
    return list(dict.fromkeys(out))


_PLACES = None
_RANK = {'city': 0, 'town': 1, 'village': 2, 'suburb': 3, 'hamlet': 4}


def _norm(t):
    t = re.sub(r'[\u064b-\u0652\u0640]', '', str(t or '')).strip().lower()
    t = t.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا').replace('ة', 'ه').replace('ى', 'ي')
    t = re.sub(r'^(مدينه|محافظه|قريه|بلده|منطقه)\s+', '', t)
    t = re.sub(r'^ال', '', t)
    return re.sub(r'\s+', ' ', t)


def _load_places():
    global _PLACES
    if _PLACES is None:
        _PLACES = {}
        try:
            import csv
            import os
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'places.csv')
            with open(path, encoding='utf-8-sig') as f:
                for r in csv.DictReader(f):
                    item = (_RANK.get(r['place'], 5), float(r['lat']), float(r['lon']), r['name'])
                    for k in (_norm(r['name']), _norm(r['name_en'])):
                        if k and (k not in _PLACES or item[0] < _PLACES[k][0]):
                            _PLACES[k] = item
        except Exception:
            pass
    return _PLACES


def _geocode_local(name):
    it = _load_places().get(_norm(name))
    return (it[1], it[2], it[3]) if it else None


def geocode(name, alt_names=()):
    """(lat, lon, الاسم) داخل السعودية، أو None. يجرّب Open-Meteo ثم OpenStreetMap بصيغ الاسم المختلفة
    (alt_names: أسماء بديلة مثل الاسم بالإنجليزي من Claude)."""
    names = _variants(name) + [a for a in alt_names if a]
    for n in names:
        res = _geocode_local(n)
        if res:
            return res
    for n in names:
        res = _geocode_open_meteo(n)
        if res:
            return res
    for n in names:
        res = _geocode_nominatim(n)
        if res:
            return res
    return None


def osrm_long(points):
    """مسار طريق بين نقطتين أو أكثر. يرجع (خط [[lat,lon]]، كم، دقائق) أو None."""
    path = ';'.join(f'{lon},{lat}' for lat, lon in points)
    try:
        r = requests.get(OSRM + path, params={'overview': 'full', 'geometries': 'geojson', 'steps': 'false'},
                         headers=extras.HEADERS, timeout=30)
        r.raise_for_status()
        rt = r.json()['routes'][0]
        line = [[c[1], c[0]] for c in rt['geometry']['coordinates']]
        return line, round(rt['distance'] / 1000, 1), round(rt['duration'] / 60)
    except Exception:
        return None


# ------------------------------------------------------------- التحليل (بدون شبكة)
def _hav(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2) - np.radians(lon1)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def resample(line, step=1.0):
    """يعيد أخذ عينات من الخط كل ~step كم. يرجع (s، lat، lon، الإجمالي) حيث s المسافة التراكمية."""
    pts = np.asarray(line, dtype=float)
    seg = _hav(pts[:-1, 0], pts[:-1, 1], pts[1:, 0], pts[1:, 1])
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(cum[-1])
    n = max(2, int(total / step) + 1)
    s = np.linspace(0.0, total, n)
    return s, np.interp(s, cum, pts[:, 0]), np.interp(s, cum, pts[:, 1]), total


def along_route(s, lat, lon, plats, plons, max_km):
    """النقاط القريبة من الطريق. يرجع قائمة (فهرس_النقطة، كم_على_الطريق، البعد_عن_الطريق) مرتبة بالكم."""
    plats, plons = np.asarray(plats, dtype=float), np.asarray(plons, dtype=float)
    if len(plats) == 0:
        return []
    deg = max_km / 100.0 + 0.05
    keep = np.where((plats > lat.min() - deg) & (plats < lat.max() + deg) &
                    (plons > lon.min() - deg) & (plons < lon.max() + deg))[0]
    out = []
    for i in range(0, len(keep), 400):
        idx = keep[i:i + 400]
        d = extras.haversine_matrix(plats[idx], plons[idx], lat, lon)   # (نقاط × عينات)
        j = d.argmin(axis=1)
        dm = d[np.arange(len(idx)), j]
        for t in np.where(dm <= max_km)[0]:
            out.append((int(idx[t]), float(s[j[t]]), float(dm[t])))
    out.sort(key=lambda x: x[1])
    return out


def cluster(items, gap=CLUSTER_KM):
    """يدمج النقاط المتجاورة على الطريق، ويبقي الأقرب للطريق من كل مجموعة."""
    groups, cur = [], []
    for it in items:
        if cur and it[1] - cur[-1][1] > gap:
            groups.append(cur)
            cur = []
        cur.append(it)
    if cur:
        groups.append(cur)
    return [min(g, key=lambda x: x[2]) for g in groups]


def refuel_plan(fuel_kms, total, safe):
    """توقفات تعبئة مقترحة: دائماً أبعد محطة داخل المدى الآمن. يرجع قائمة كم. الخزان ممتلئ عند البداية."""
    stops, pos = [], 0.0
    ks = sorted(fuel_kms)
    while total - pos > safe:
        reach = [k for k in ks if pos < k <= pos + safe]
        if reach:
            nxt = max(reach)
        else:
            nearer = [k for k in ks if k > pos]
            if not nearer:
                break
            nxt = min(nearer)          # لا محطة داخل المدى: نقطة خطر، نتوجه لأقرب محطة
        stops.append(nxt)
        pos = nxt
    return stops


def gaps(fuel_kms, total, rng, safe):
    """المقاطع بين المحطات. level: ok / warn (تتجاوز المدى الآمن) / danger (تتجاوز مدى السيارة)."""
    pts = [0.0] + sorted(fuel_kms) + [total]
    out = []
    for a, b in zip(pts[:-1], pts[1:]):
        g = b - a
        level = 'danger' if g > rng else ('warn' if g > safe else 'ok')
        out.append({'from': a, 'to': b, 'km': g, 'level': level})
    return out


def analyze(line, minutes, fuel, hosp, rng=DEFAULT_RANGE):
    """fuel / hosp: (lats، lons). يرجع نتائج الطول والمحطات والفجوات بدون أسماء (الأسماء تُضاف خارجها)."""
    s, lat, lon, total = resample(line)
    safe = rng * RESERVE
    f_items = cluster(along_route(s, lat, lon, fuel[0], fuel[1], FUEL_CORRIDOR_KM))
    h_items = cluster(along_route(s, lat, lon, hosp[0], hosp[1], HOSP_CORRIDOR_KM), gap=3.0)
    f_kms = [k for _, k, _ in f_items]
    plan_kms = refuel_plan(f_kms, total, safe)
    gp = gaps(f_kms, total, rng, safe)
    worst = max(gp, key=lambda g: g['km'])
    verdict = 'danger' if any(g['level'] == 'danger' for g in gp) else (
        'warn' if any(g['level'] == 'warn' for g in gp) else 'ok')
    h_pts = [0.0] + [k for _, k, _ in h_items] + [total]
    h_gap = max((b - a for a, b in zip(h_pts[:-1], h_pts[1:])), default=total)

    def at(km):
        i = int(np.clip(round(km / max(total, 1e-6) * (len(s) - 1)), 0, len(s) - 1))
        return float(lat[i]), float(lon[i])

    return {'total_km': total, 'safe_km': safe, 'range_km': rng, 'f_items': f_items, 'h_items': h_items,
            'plan_kms': plan_kms, 'gaps': gp, 'worst': worst, 'verdict': verdict, 'hosp_gap_km': h_gap,
            'minutes': minutes, 's': s, 'lat': lat, 'lon': lon, 'at': at}


# ------------------------------------------------------------- الخطة الكاملة
def _valid(gdf):
    return gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]


def make_plan(text, loc, layers, range_default=DEFAULT_RANGE):
    """يرجع dict جاهزاً للعرض (بدون تحويل أسماء العرض) أو {'error': ...}."""
    if 'fuel' not in layers or len(layers['fuel']) == 0:
        return {'error': 'طبقة محطات الوقود غير موجودة في البيانات.'}
    try:
        req = parse_request(text)
    except Exception:
        return {'error': 'ما قدرت أفهم طلبك الحين. جرّب مثل: من الرياض لأبها وسيارتي تقطع 450 كم.'}
    if not req.get('dest'):
        return {'error': 'ما عرفت وجهتك. جرّب مثل: من الرياض لأبها وسيارتي تقطع 450 كم.'}

    dest = geocode(req['dest'], (req.get('dest_en'),))
    if not dest:
        return {'error': f"ما لقيت «{req['dest']}» على الخريطة. جرّب كتابة اسم المدينة بشكل ثاني."}
    if req.get('origin'):
        org = geocode(req['origin'], (req.get('origin_en'),))
        if not org:
            return {'error': f"ما لقيت «{req['origin']}» على الخريطة. جرّب كتابة اسم المدينة بشكل ثاني."}
    elif loc:
        org = (float(loc[0]), float(loc[1]), 'موقعك')
    else:
        return {'error': 'حدد موقعك أو اكتب مدينة البداية، مثل: من الرياض لأبها.'}

    route = osrm_long([(org[0], org[1]), (dest[0], dest[1])])
    if not route:
        return {'error': 'تعذّر حساب مسار الطريق الحين. حاول بعد شوي.'}
    line, km, minutes = route
    if km < 20:
        return {'error': 'الوجهة قريبة جداً. هذه الميزة للرحلات البرية الطويلة، استخدم تخطيط مشوار للمشاوير داخل المدينة.'}

    rng = float(req.get('range_km') or range_default)
    rng = min(max(rng, 100.0), 1500.0)

    fg = _valid(layers['fuel'])
    fl, fo = extras.coords('fuel', layers['fuel'])
    if 'hospitals' in layers and len(layers['hospitals']):
        hl, ho = extras.coords('hospitals', layers['hospitals'])
        hg = _valid(layers['hospitals'])
    else:
        hl, ho, hg = np.array([]), np.array([]), None

    res = analyze(line, minutes, (fl, fo), (hl, ho), rng)
    total = res['total_km']

    def eta(k):
        return int(round(minutes * k / max(total, 1e-6))) if minutes else None

    def fuel_pt(item):
        i, k, d = item
        return {'km': round(k, 1), 'lat': round(float(fl[i]), 5), 'lon': round(float(fo[i]), 5),
                'name': extras._name_of(fg.iloc[i]), 'off_km': round(d, 1)}

    f_all = [fuel_pt(it) for it in res['f_items']]
    by_km = {round(p['km'], 1): p for p in f_all}
    plan = []
    for n, k in enumerate(res['plan_kms'], 1):
        p = dict(by_km.get(round(k, 1)) or {})
        prev = res['plan_kms'][n - 2] if n > 1 else 0.0
        p.update({'n': n, 'eta_min': eta(k), 'since_km': round(k - prev, 1)})
        plan.append(p)
    last_stop = res['plan_kms'][-1] if res['plan_kms'] else 0.0

    hosp = []
    if hg is not None:
        for i, k, d in res['h_items'][:80]:
            hosp.append({'km': round(k, 1), 'lat': round(float(hl[i]), 5), 'lon': round(float(ho[i]), 5),
                         'name': extras._name_of(hg.iloc[i])})

    segs = []
    for g in res['gaps']:
        if g['level'] == 'ok':
            continue
        a, b = g['from'], g['to']
        m = (res['s'] >= a) & (res['s'] <= b)
        pts = [[round(float(x), 5), round(float(y), 5)] for x, y in zip(res['lat'][m], res['lon'][m])]
        step = max(1, len(pts) // 120)
        segs.append({'from': round(a, 1), 'to': round(b, 1), 'km': round(g['km'], 1), 'level': g['level'],
                     'line': pts[::step] + ([pts[-1]] if pts and (len(pts) - 1) % step else [])})

    worst = res['worst']
    wa = next((p for p in f_all if abs(p['km'] - worst['from']) < 0.06), None)
    wb = next((p for p in f_all if abs(p['km'] - worst['to']) < 0.06), None)
    step = max(1, -(-len(line) // 500))
    return {'text': text, 'origin': {'name': org[2], 'pt': [org[0], org[1]]},
            'dest': {'name': dest[2], 'pt': [dest[0], dest[1]]}, 'km': km, 'minutes': minutes,
            'range_km': rng, 'safe_km': round(res['safe_km']), 'range_given': bool(req.get('range_km')),
            'line': [[round(p[0], 5), round(p[1], 5)] for p in line[::step]] + [[round(line[-1][0], 5), round(line[-1][1], 5)]],
            'fuel': f_all[:200], 'plan': plan, 'segments': segs, 'verdict': res['verdict'],
            'worst': {'km': round(worst['km'], 1), 'from_km': round(worst['from'], 1), 'to_km': round(worst['to'], 1),
                      'from_name': (wa or {}).get('name') or ('نقطة البداية' if worst['from'] < 0.1 else None),
                      'to_name': (wb or {}).get('name') or ('الوجهة' if worst['to'] > total - 0.1 else None),
                      'level': worst['level']},
            'end_left_km': round(total - last_stop, 1), 'fuel_count': len(f_all),
            'hosp': hosp, 'hosp_gap_km': round(res['hosp_gap_km'], 1)}