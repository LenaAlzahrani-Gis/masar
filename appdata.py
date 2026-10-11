"""مسار: تجهيز البيانات التي تُرسل إلى واجهة الخريطة (masar_ui)."""
import json

import extras
import ui

CAP = 120                      # أقرب عدد عناصر لكل فئة يُرسل للمتصفح
DEFAULT_CENTER = (24.0, 45.0)

TOOL_TEXT = {
    'layers_info': 'تحققت من البيانات المتوفرة',
    'clip_layer': 'قصصت الطبقة بحدود محددة',
    'count_in_polygons': 'حسبت العدد داخل كل منطقة',
    'summarize_layer': 'لخّصت الطبقة',
}


def _f(x, nd=5):
    return round(float(x), nd)


def _short(name, n=46):
    name = str(name)
    return name if len(name) <= n else name[:n - 1] + '…'


def _lines_for(gdf, center, max_lines=250, max_km=450):
    out = []
    try:
        g = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
        geoms = g.geometry.simplify(0.003).tolist()
    except Exception:
        return out
    scored = []
    for geom in geoms:
        parts = list(geom.geoms) if hasattr(geom, 'geoms') else [geom]
        for part in parts:
            c = list(part.coords)
            if len(c) < 2:
                continue
            d = float(extras.haversine_1(center[0], center[1], [c[0][1]], [c[0][0]])[0])
            if d <= max_km:
                scored.append((d, [[_f(y, 4), _f(x, 4)] for x, y in c]))
    scored.sort(key=lambda t: t[0])
    return [ln for _, ln in scored[:max_lines]]


def member_data(key, gdf, center):
    meta = ui.CAT[key]
    m = {'key': key, 'label': meta['label'], 'icon': meta['icon'], 'color': meta['color'],
         'big': key == 'haramain', 'pts': [], 'lines': []}
    if key in ui.LINE_LAYERS:
        m['lines'] = _lines_for(gdf, center)
        return m
    lats, lons = extras.coords(key, gdf)
    if len(lats) == 0:
        return m
    d = extras.haversine_1(center[0], center[1], lats, lons)
    idx = d.argsort()[:CAP]
    g = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].iloc[idx]
    cols = [c for c in ('name:ar', 'name', 'name:en') if c in g.columns]
    data = {c: g[c].tolist() for c in cols}
    for j, i in enumerate(idx):
        nm = ui.display_name(ui.row_name({c: data[c][j] for c in cols}, cols), key)
        m['pts'].append([_f(lats[i]), _f(lons[i]), _short(nm), round(float(d[i]), 2)])
    return m


def build_cats(layers, loc):
    center = tuple(loc) if loc else DEFAULT_CENTER
    cats = []
    for gtitle, keys in ui.GROUPS:
        for k in keys:
            if not ui.pill_available(k, layers):
                continue
            members = ui.MERGED[k][3] if k in ui.MERGED else [k]
            ms_ = [member_data(mk, layers[mk], center) for mk in members if mk in layers and len(layers[mk])]
            if not ms_:
                continue
            meta = ui.CAT[k]
            cats.append({'key': k, 'label': meta['label'], 'icon': meta['icon'], 'color': meta['color'],
                         'group': gtitle, 'members': ms_})
    return cats


def steps_ar(log):
    out = []
    for s in log:
        tool, a = s.get('tool'), (s.get('args') or {})
        res = s.get('result')
        if tool == 'nearest_to_point':
            lab = ui.AR_NAMES.get(a.get('layer'), 'الخدمة')
            out.append({'t': f"بحثت عن أقرب {a.get('k', 3)} من «{lab}» حول موقعك"})
            if isinstance(res, dict) and res.get('results') and res['results'][0].get('minutes') is not None:
                out.append({'t': 'حسبت المسار والزمن على شبكة الطرق (تقريبي بدون حالة المرور)'})
            tool_txt = None
        elif tool == 'buffer_layer':
            out.append({'t': f"رسمت نطاقاً بمسافة {a.get('distance_m', '')} م"})
        elif tool == 'select_by_distance':
            out.append({'t': f"اخترت ما يقع ضمن {a.get('max_distance_m', '')} م"})
        else:
            out.append({'t': TOOL_TEXT.get(tool, 'نفّذت خطوة تحليل')})
        out[-1]['tool'] = tool
        try:
            out[-1]['args'] = json.dumps(a, ensure_ascii=False)[:180]
        except Exception:
            out[-1]['args'] = ''
    return out


def build_answer(entry, nearest, layers):
    """entry: إدخال السجل. nearest: نتائج nearest_to_point. يرجع dict لواجهة الخريطة."""
    ans = {'id': entry['id'], 'req': entry['req'], 'text': entry['text'], 'secs': entry.get('secs'),
           'steps': steps_ar(entry['log']), 'results': [], 'routes': [], 'rings': False}
    geoms = entry.get('geoms') or {}
    for e in nearest:
        res = e['result']
        layer = res.get('layer')
        meta = ui.CAT.get(layer, {})
        lg = geoms.get(layer, [])
        for i, r in enumerate(res['results']):
            km = r['road_km'] if r.get('minutes') is not None else r['straight_km']
            ans['results'].append({
                'key': layer, 'name': ui.display_name(r.get('name'), layer), 'lat': _f(r['lat']), 'lon': _f(r['lon']),
                'km': round(float(km), 1), 'min': r.get('minutes'), 'icon': meta.get('icon', 'location_on'),
                'color': meta.get('color', '#9b2c22'), 'label': ui.SINGULAR.get(layer, meta.get('label', ''))})
            line = lg[i] if i < len(lg) else None
            if line:
                ans['routes'].append({'pts': [[_f(p[0], 5), _f(p[1], 5)] for p in line][:1200], 'straight': False})
            else:
                a = e['args']
                ans['routes'].append({'pts': [[_f(a['lat']), _f(a['lon'])], [_f(r['lat']), _f(r['lon'])]],
                                      'straight': True})
        ans['rings'] = True
    # طبقة ناتجة عن تحليل (بدون أقرب نتائج)
    layer = entry.get('layer')
    if not nearest and layer and layer in layers and len(layers[layer]) > 0:
        try:
            g = layers[layer].head(1500).copy()
            cols = [c for c in ('name:ar', 'name', 'name:en') if c in g.columns][:1]
            g = g[cols + ['geometry']]
            g['geometry'] = g.geometry.simplify(0.0008)
            ans['geojson'] = json.loads(g.to_json())
        except Exception:
            pass
    return ans


def trip_payload(plan):
    """يحوّل خطة المشوار إلى بيانات خفيفة للواجهة."""
    if not plan:
        return None
    if plan.get('error'):
        return {'id': plan.get('id'), 'error': plan['error']}
    line = plan.get('line') or []
    step = max(1, len(line) // 400)
    pts = [[round(p[0], 5), round(p[1], 5)] for p in line[::step]]
    if line and pts[-1] != [round(line[-1][0], 5), round(line[-1][1], 5)]:
        pts.append([round(line[-1][0], 5), round(line[-1][1], 5)])
    stops = []
    for s in plan.get('stops', []):
        meta = ui.CAT.get(s['key'], {})
        stops.append({'key': s['key'], 'name': ui.display_name(s['name'], s['key']),
                      'lat': s['lat'], 'lon': s['lon'], 'icon': meta.get('icon', 'location_on'),
                      'color': meta.get('color', '#9b2c22'),
                      'label': ui.SINGULAR.get(s['key'], meta.get('label', ''))})
    return {'id': plan.get('id'), 'text': plan.get('text'), 'origin': plan.get('origin'), 'stops': stops,
            'line': pts, 'km': plan.get('km'), 'minutes': plan.get('minutes'),
            'straight': bool(plan.get('straight_only')), 'reordered': bool(plan.get('reordered'))}


def road_payload(plan):
    """يحوّل خطة رحلة البر إلى بيانات جاهزة للواجهة (أسماء العرض + أرقام فقط)."""
    if not plan:
        return None
    if plan.get('error'):
        return {'id': plan.get('id'), 'error': plan['error']}

    def nm(n):
        return ui.display_name(n, 'fuel')

    out = dict(plan)
    out['fuel'] = [dict(f, name=nm(f.get('name'))) for f in plan.get('fuel', [])]
    out['plan'] = [dict(p, name=nm(p.get('name'))) for p in plan.get('plan', [])]
    out['hosp'] = [dict(h, name=ui.display_name(h.get('name'), 'hospitals')) for h in plan.get('hosp', [])]
    w = dict(plan.get('worst') or {})
    w['from_name'] = nm(w.get('from_name')) if w.get('from_name') not in (None, 'نقطة البداية', 'الوجهة') else w.get('from_name')
    w['to_name'] = nm(w.get('to_name')) if w.get('to_name') not in (None, 'نقطة البداية', 'الوجهة') else w.get('to_name')
    out['worst'] = w
    return out


def compare_payload(ra, rb, a, b, cid):
    """مقارنة درجة الوصول بين موقعين."""
    if not ra or not rb:
        return {'id': cid, 'error': 'ما توفرت بيانات كافية لمقارنة هذين الموقعين.'}
    rows_b = {r['key']: r for r in rb['rows']}
    rows = []
    for r in ra['rows']:
        o = rows_b.get(r['key'])
        if not o:
            continue
        meta = ui.CAT.get(r['key'], {})
        rows.append({'key': r['key'], 'label': ui.AR_NAMES.get(r['key'], meta.get('label', r['key'])),
                     'icon': meta.get('icon', 'location_on'),
                     'a_km': round(r['nearest_km'], 1), 'b_km': round(o['nearest_km'], 1),
                     'a_cnt': r['count'], 'b_cnt': o['count']})
    return {'id': cid, 'a': {'pt': a, 'score': ra['score'], 'label': ra['label']},
            'b': {'pt': b, 'score': rb['score'], 'label': rb['label']}, 'rows': rows}