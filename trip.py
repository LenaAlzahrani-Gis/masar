"""مسار: تخطيط مشوار من جملة واحدة (Claude يستخرج المحطات، والباقي حساب محلي)."""
import itertools
import json
import re

import requests

import extras

MODEL = 'claude-sonnet-5-5'
OSRM = 'https://router.project-osrm.org/route/v1/driving/'
MAX_STOPS = 5

# المحطات المسموحة في المشوار (نقطية فقط)
TRIP_LABELS = {
    'fuel': 'محطة وقود', 'malls': 'مول أو مركز تسوق', 'supermarkets': 'سوبرماركت', 'groceries': 'بقالة',
    'restaurants': 'مطعم', 'mosques': 'مسجد', 'pharmacies': 'صيدلية', 'hospitals': 'مستشفى',
    'clinics': 'عيادة', 'parks': 'حديقة', 'tourism': 'معلم سياحي', 'schools': 'مدرسة',
    'police': 'مركز شرطة', 'civil_defense': 'دفاع مدني', 'airports': 'مطار',
    'train_stations': 'محطة قطار', 'doctors': 'مركز طبي',
}


def parse_stops(text, available):
    """يرجع (قائمة المفاتيح بالترتيب، هل الترتيب محدد صراحة)."""
    import anthropic

    allowed = {k: v for k, v in TRIP_LABELS.items() if k in available}
    system = (
        'حوّل وصف المشوار إلى JSON فقط بدون أي شرح، بالشكل: '
        '{"stops": ["key1", "key2"], "ordered": true}. '
        'stops هي أنواع المحطات بالترتيب الذي ذكره المستخدم، ومن هذه المفاتيح فقط: '
        + json.dumps(allowed, ensure_ascii=False) +
        f'. الحد الأقصى {MAX_STOPS} محطات. ordered تكون true فقط إذا حدد المستخدم الترتيب صراحة '
        '(مثل: أولاً، ثم، بعدها)، وإلا false. إذا لم تجد أي محطة مناسبة فأرجع {"stops": [], "ordered": false}.')
    client = anthropic.Anthropic()
    msg = client.messages.create(model=MODEL, max_tokens=300, system=system,
                                 messages=[{'role': 'user', 'content': text}])
    raw = ''.join(b.text for b in msg.content if getattr(b, 'type', '') == 'text')
    m = re.search(r'\{.*\}', raw, re.S)
    data = json.loads(m.group(0)) if m else {}
    stops = []
    for k in data.get('stops', []):
        if k in allowed and k not in stops:
            stops.append(k)
    return stops[:MAX_STOPS], bool(data.get('ordered'))


def _greedy(loc, seq, layers):
    """يختار أقرب نقطة لكل محطة بالتتابع. يرجع (المجموع كم، [(فهرس، lat، lon)])."""
    cur, total, picks = loc, 0.0, []
    for key in seq:
        lats, lons = extras.coords(key, layers[key])
        d = extras.haversine_1(cur[0], cur[1], lats, lons)
        i = int(d.argmin())
        total += float(d[i])
        cur = (float(lats[i]), float(lons[i]))
        picks.append((i, cur[0], cur[1]))
    return total, picks


def best_sequence(loc, stops, ordered, layers):
    if ordered or len(stops) <= 1:
        return list(stops)
    best, best_len = None, None
    for perm in itertools.permutations(stops):
        length, _ = _greedy(loc, perm, layers)
        if best_len is None or length < best_len:
            best, best_len = list(perm), length
    return best


def osrm_route(points):
    """points: [(lat, lon)]. يرجع (خط المسار، كم، دقائق) أو None."""
    path = ';'.join(f'{lon},{lat}' for lat, lon in points)
    try:
        r = requests.get(OSRM + path, params={'overview': 'full', 'geometries': 'geojson'},
                         headers=extras.HEADERS, timeout=12)
        r.raise_for_status()
        rt = r.json()['routes'][0]
        line = [[c[1], c[0]] for c in rt['geometry']['coordinates']]
        return line, round(rt['distance'] / 1000, 1), round(rt['duration'] / 60)
    except Exception:
        return None


def make_plan(text, loc, layers):
    """layers: {المفتاح: GeoDataFrame}. يرجع dict جاهز للعرض أو {'error': ...}."""
    stops, ordered = parse_stops(text, set(layers))
    if not stops:
        return {'error': 'ما قدرت أحدد محطات من طلبك. جرّب مثل: أبغى أعبّي بنزين وأروح المول وأصلّي.'}
    seq = best_sequence(loc, stops, ordered, layers)
    _, picks = _greedy(loc, seq, layers)
    out_stops = []
    for key, (i, lat, lon) in zip(seq, picks):
        row = layers[key].iloc[i]
        out_stops.append({'key': key, 'name': extras._name_of(row), 'lat': lat, 'lon': lon})
    pts = [tuple(loc)] + [(s['lat'], s['lon']) for s in out_stops]
    route = osrm_route(pts)
    if route:
        line, km, minutes = route
        approx = False
    else:
        line, approx = [list(p) for p in pts], True
        km = round(sum(float(extras.haversine_1(a[0], a[1], [b[0]], [b[1]])[0])
                       for a, b in zip(pts[:-1], pts[1:])), 1)
        minutes = None
    return {'text': text, 'origin': list(loc), 'stops': out_stops, 'line': line,
            'km': km, 'minutes': minutes, 'straight_only': approx, 'reordered': (not ordered and seq != stops)}