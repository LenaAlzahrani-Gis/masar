import html
import math

import folium
from folium.plugins import Fullscreen, MarkerCluster

import ui

TILES = 'OpenStreetMap'
COLORS = ['#2563eb', '#16a34a', '#9333ea', '#ea580c', '#b91c1c']

NORTH_HTML = '''
<div style="position:absolute;top:10px;right:10px;z-index:9999;width:44px;height:44px;
  border-radius:50%;background:rgba(255,255,255,.95);border:1px solid #94a3b8;
  box-shadow:0 1px 5px rgba(0,0,0,.3);display:flex;flex-direction:column;align-items:center;
  justify-content:center;font:700 12px/1 'Segoe UI',Tahoma,sans-serif;color:#0f172a;
  pointer-events:none;">
  <span style="margin-bottom:2px">N</span>
  <svg width="14" height="16" viewBox="0 0 14 16"><polygon points="7,0 14,16 7,12 0,16" fill="#dc2626"/></svg>
</div>
'''

MAP_CSS = '''
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,500,1,0&display=block">
<style>
.ms{font-family:'Material Symbols Rounded';font-weight:normal;font-style:normal;line-height:1;letter-spacing:normal;
  text-transform:none;display:inline-block;white-space:nowrap;direction:ltr;font-feature-settings:'liga';
  -webkit-font-smoothing:antialiased;}
.mz-pin{position:relative;border-radius:50%;background:var(--c);color:#fff;border:2px solid #fff;
  box-shadow:0 2px 8px rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;
  transition:transform .15s ease;}
.mz-pin:hover{transform:translate(-50%,-50%) scale(1.12) !important;}
.mz-pin.pulse::after{content:'';position:absolute;inset:-7px;border-radius:50%;border:2px solid var(--c);
  animation:mzp 1.8s ease-out infinite;}
@keyframes mzp{0%{transform:scale(.75);opacity:.9}100%{transform:scale(1.6);opacity:0}}
.leaflet-tooltip{background:#fff;color:#10262a;border:none;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,.22);
  font:600 11.5px 'IBM Plex Sans Arabic',Tahoma,sans-serif;padding:3px 8px;}
.leaflet-tooltip-bottom:before,.leaflet-tooltip-top:before{display:none}
.leaflet-container{font-family:'IBM Plex Sans Arabic',Tahoma,sans-serif}
</style>
'''

DARK_MAP_CSS = '''
<style>
.base-osm{filter:invert(1) hue-rotate(180deg) brightness(.92) contrast(.9);}
.leaflet-container{background:#1b2430;}
</style>
'''

USER_ICON_HTML = '''
<style>@keyframes lp {0% {transform: scale(1); opacity: .7;} 100% {transform: scale(3.2); opacity: 0;}}</style>
<div style="position:relative;width:0;height:0;">
  <div style="position:absolute;left:-11px;top:-11px;width:22px;height:22px;border-radius:50%;
              background:#1a73e8;animation:lp 1.8s ease-out infinite;"></div>
  <div style="position:absolute;left:-11px;top:-11px;width:22px;height:22px;border-radius:50%;
              background:#1a73e8;border:3px solid white;box-sizing:border-box;
              box-shadow:0 0 6px rgba(0,0,0,.5);"></div>
  <div style="position:absolute;left:0;top:16px;transform:translateX(-50%);background:#1a73e8;
              color:white;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:700;
              white-space:nowrap;box-shadow:0 1px 4px rgba(0,0,0,.4);direction:rtl;">موقعك</div>
</div>
'''


def pin_html(icon, color, size=30, pulse=False):
    cls = 'mz-pin pulse' if pulse else 'mz-pin'
    return (f'<div class="{cls}" style="--c:{color};width:{size}px;height:{size}px;transform:translate(-50%,-50%);">'
            f'<span class="ms" style="font-size:{round(size * 0.58)}px">{icon}</span></div>')


def _pill(dark):
    bg, ink, line = ('#1f2937', '#e5e7eb', '#4b5563') if dark else ('#ffffff', '#222222', '#888888')
    return (f'background:{bg};color:{ink};border:1px solid {line};border-radius:10px;'
            'padding:1px 7px;font-size:12px;font-weight:600;white-space:nowrap;direction:rtl;')


def base_map(center, zoom, dark=False):
    m = folium.Map(location=center, zoom_start=zoom, tiles=None, control_scale=True, zoom_control='topright')
    folium.TileLayer(TILES, name='خريطة الشوارع', control=True, className='base-osm').add_to(m)
    folium.TileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri, Maxar, Earthstar Geographics', name='صورة فضائية', control=True).add_to(m)
    Fullscreen(position='topright', title='ملء الشاشة', title_cancel='إغلاق').add_to(m)
    m.get_root().html.add_child(folium.Element(NORTH_HTML))
    m.get_root().header.add_child(folium.Element(MAP_CSS))
    if dark:
        m.get_root().header.add_child(folium.Element(DARK_MAP_CSS))
    return m


def focus_marker(m, loc, f, dark=False):
    """يبرز مكاناً اختاره المستخدم (من درجة الوصول): علامة كبيرة وخط مباشر من موقعه."""
    dest = [f['lat'], f['lon']]
    meta = ui.CAT.get(f['key'], {})
    col = meta.get('color', '#c58f2d')
    name = ui.display_name(f['name'], f['key'])
    folium.PolyLine([loc, dest], color='#c58f2d', weight=3, dash_array='8 8', opacity=.95).add_to(m)
    icon_html = pin_html(meta.get('icon', 'location_on'), col, 42, pulse=True)
    folium.Marker(dest, icon=folium.DivIcon(html=icon_html, icon_size=(0, 0), icon_anchor=(0, 0)),
                  tooltip=folium.Tooltip(html.escape(name), permanent=True, direction='bottom', offset=(0, 4)),
                  zIndexOffset=1200).add_to(m)
    mid = [(loc[0] + dest[0]) / 2, (loc[1] + dest[1]) / 2]
    folium.Marker(mid, icon=folium.DivIcon(
        html=f'<div style="{_pill(dark)}transform:translate(-50%,-50%);">{f["km"]:,.1f} كم</div>',
        icon_size=(0, 0), icon_anchor=(0, 0))).add_to(m)
    m.fit_bounds([loc, dest], padding=(70, 70), max_zoom=16)


def finish(m):
    """يضيف زر تبديل الخلفية والطبقات. يُستدعى مرة واحدة بعد إضافة كل الطبقات."""
    folium.LayerControl(position='topleft', collapsed=True).add_to(m)
    return m


def user_marker(m, loc, accuracy=None, rings=False):
    if accuracy and accuracy > 50:
        folium.Circle(loc, radius=min(accuracy, 5000), color='#1a73e8', weight=1,
                      fill=True, fill_opacity=0.08).add_to(m)
    if rings:
        for r in (1000, 3000, 5000):
            folium.Circle(loc, radius=r, color='#c8963e', weight=1.5, dash_array='5 6',
                          fill=False, tooltip=f'{r // 1000} كم').add_to(m)
    folium.Marker(
        loc, tooltip='موقعك', zIndexOffset=1000,
        icon=folium.DivIcon(html=USER_ICON_HTML, icon_size=(0, 0), icon_anchor=(0, 0)),
    ).add_to(m)


def nearest_indices(xs, ys, center, cap):
    """فهارس أقرب cap نقطة إلى center (خط عرض، خط طول) بتقريب مستوٍ."""
    import numpy as np
    k = math.cos(math.radians(center[0]))
    d = ((np.asarray(xs) - center[1]) * k) ** 2 + (np.asarray(ys) - center[0]) ** 2
    return np.argsort(d)[:cap]


def _names(sub, layer):
    cols = [c for c in ('name:ar', 'name', 'name:en') if c in sub.columns]
    data = {c: sub[c].tolist() for c in cols}
    out = []
    for i in range(len(sub)):
        out.append(ui.display_name(ui.row_name({c: data[c][i] for c in cols}, cols), layer))
    return out


def haversine_km(lat1, lon1, lat2, lon2):
    import numpy as np
    p1, p2 = np.radians(lat1), np.radians(np.asarray(lat2))
    dl = np.radians(np.asarray(lon2) - lon1)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def nearby_list(layers, loc, n=8):
    """أقرب n معلم من كل فئة نقطية (مسافة خط مباشر بالكيلومتر). يرجع [(عنوان، [(اسم، كم)])]."""
    blocks = []
    for key, gdf in layers.items():
        meta = ui.CAT.get(key)
        if meta is None or key in ui.LINE_LAYERS or len(gdf) == 0:
            continue
        g = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
        pts = g.geometry.representative_point()
        xs, ys = pts.x.to_numpy(), pts.y.to_numpy()
        d = haversine_km(loc[0], loc[1], ys, xs)
        idx = d.argsort()[:n]
        names = _names(g.iloc[idx], key)
        blocks.append((meta['label'], [(names[j], float(d[i])) for j, i in enumerate(idx)]))
    return blocks


def haversine_idx(center, lats, lons):
    import numpy as np
    return np.asarray(haversine_km(center[0], center[1], lats, lons))


def nearby_for(selected, layers, loc, n=8):
    """قوائم الأقرب إليك للأيقونات المختارة. الطبقات المرتبطة تُدمج في قائمة واحدة،
    والطبقة الصغيرة جداً (مثل الحرمين) تظهر كاملة في آخر القائمة مهما بعدت."""
    blocks = []
    for k in selected:
        members = ui.MERGED[k][3] if k in ui.MERGED else [k]
        big, small = [], []
        for m in members:
            if m not in layers:
                continue
            for _, rows in nearby_list({m: layers[m]}, loc, n):
                (small if len(layers[m]) <= 5 else big).extend(rows)
        parts = sorted(big, key=lambda r: r[1])[:n] + sorted(small, key=lambda r: r[1])
        if parts:
            blocks.append((ui.CAT[k]['label'] if k in ui.CAT else k, parts))
    return blocks


def _clean(v):
    return v.strip() if isinstance(v, str) and v.strip() and v.strip().lower() != 'nan' else None


def nearby_items(keys, layers, loc, n=8):
    """عناصر للأماكن الأقرب (مع النوع والوصف) لعرض بطاقة التفاصيل. الطبقة الصغيرة تظهر كاملة."""
    items = []
    for key in keys:
        gdf = layers.get(key)
        if gdf is None or len(gdf) == 0:
            continue
        g = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
        pts = g.geometry.representative_point()
        d = haversine_idx(loc, pts.y.to_numpy(), pts.x.to_numpy())
        idx = d.argsort()[: (len(g) if len(g) <= 5 else n)]
        sub = g.iloc[idx]
        names = _names(sub, key)
        kinds = sub['kind'].tolist() if 'kind' in sub.columns else [None] * len(sub)
        descs = sub['description'].tolist() if 'description' in sub.columns else [None] * len(sub)
        extra = {c: (sub[c].tolist() if c in sub.columns else [None] * len(sub))
                 for c in ('wikipedia', 'wikidata', 'commons')}
        ptsub = pts.iloc[idx]
        arn = sub['name:ar'].tolist() if 'name:ar' in sub.columns else [None] * len(sub)
        enn = sub['name:en'].tolist() if 'name:en' in sub.columns else [None] * len(sub)
        for j, i in enumerate(idx):
            items.append({'key': key, 'name': names[j], 'km': float(d[i]),
                          'kind': _clean(kinds[j]), 'desc': _clean(descs[j]),
                          'wikipedia': _clean(extra['wikipedia'][j]), 'wikidata': _clean(extra['wikidata'][j]),
                          'commons': _clean(extra['commons'][j]),
                          'lat': float(ptsub.y.iloc[j]), 'lon': float(ptsub.x.iloc[j]),
                          'names': [_clean(arn[j]), _clean(enn[j]), names[j]]})
    return items


def add_category_layers(m, layers, center, show_names=True, dark=False, cap=300, bounds=None):
    """يضيف أيقونات الخدمات المختارة (الأقرب cap لكل فئة). يرجع قائمة (الفئة، المعروض، الإجمالي)."""
    notes = []
    for key, gdf in layers.items():
        meta = ui.CAT.get(key)
        if meta is None or len(gdf) == 0:
            continue
        g = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
        if key in ui.LINE_LAYERS:
            lines = g[['geometry']].copy()
            lines['geometry'] = lines.geometry.simplify(0.002)
            folium.GeoJson(
                lines, name=meta['label'],
                style_function=lambda f, c=meta['color']: {
                    'color': '#e2e8f0' if dark else c, 'weight': 3, 'dashArray': '8 5', 'opacity': .9},
                tooltip=meta['label']).add_to(m)
            continue
        pts = g.geometry.representative_point()
        xs, ys = pts.x.to_numpy(), pts.y.to_numpy()
        idx = nearest_indices(xs, ys, center, cap)
        sub = g.iloc[idx]
        names = _names(sub, key)
        col = meta['color']
        if bounds is not None:
            bounds.extend([float(ys[i]), float(xs[i])] for i in idx[:10])
        cluster = MarkerCluster(
            name=meta['label'],
            options={'maxClusterRadius': 40, 'disableClusteringAtZoom': 16},
            icon_create_function=(
                "function(c){var n=c.getChildCount();return L.divIcon({html:'<div style=\"background:"
                + col + ";color:#fff;border:3px solid rgba(255,255,255,.92);border-radius:50%;width:38px;"
                "height:38px;display:flex;align-items:center;justify-content:center;font:700 13px sans-serif;"
                "box-shadow:0 1px 6px rgba(0,0,0,.4)\">'+n+'</div>',className:'',iconSize:[38,38]});}")
        ).add_to(m)
        dists = haversine_idx(center, ys[idx], xs[idx])
        for j, i in enumerate(idx):
            name = names[j]
            big = (key == 'haramain')           # الحرمان: علامة أكبر بلون ذهبي
            icon_html = pin_html(meta['icon'], col, 40 if big else 30, pulse=(big or j == 0))
            folium.Marker(
                [float(ys[i]), float(xs[i])],
                icon=folium.DivIcon(html=icon_html, icon_size=(0, 0), icon_anchor=(0, 0)),
                tooltip=folium.Tooltip(html.escape(name), permanent=bool(show_names or big),
                                       direction='bottom', offset=(0, 14 if not big else 22)),
                zIndexOffset=900 if big else 0,
                popup=folium.Popup(
                    f'<div style="direction:rtl;text-align:right"><b>{html.escape(name)}</b>'
                    f'<br>{html.escape(meta["label"])}</div>', max_width=220),
            ).add_to(cluster)
        notes.append((meta['label'], len(idx), len(g)))
    return notes


def nearest_map(entries, geoms, dark=False):
    first = entries[0]['args']
    origin = [first['lat'], first['lon']]
    m = base_map(origin, 12, dark)
    pill = _pill(dark)
    lats, lons = [origin[0]], [origin[1]]
    for e_i, e in enumerate(entries):
        color = COLORS[e_i % len(COLORS)]
        start = [e['args']['lat'], e['args']['lon']]
        res = e['result']
        layer_geoms = geoms.get(res['layer'], [])
        for i, r in enumerate(res['results']):
            dest = [r['lat'], r['lon']]
            line = layer_geoms[i] if i < len(layer_geoms) else None
            if line:
                folium.PolyLine(line, color=color, weight=5, opacity=0.8).add_to(m)
                lats += [p[0] for p in line]
                lons += [p[1] for p in line]
                mid = line[len(line) // 2]
            else:
                folium.PolyLine([start, dest], color=color, weight=2, dash_array='6').add_to(m)
                lats.append(dest[0])
                lons.append(dest[1])
                mid = [(start[0] + dest[0]) / 2, (start[1] + dest[1]) / 2]
            name = ui.display_name(r.get('name'), res.get('layer'))
            folium.Marker(
                mid,
                icon=folium.DivIcon(
                    html=(f'<div style="{pill}transform:translate(-50%,-50%);'
                          f'border-color:{color};">{ui.esc(ui.label_text(r))}</div>'),
                    icon_size=(0, 0), icon_anchor=(0, 0)),
            ).add_to(m)
            folium.Marker(
                dest,
                tooltip=f"{i + 1}. {name} — {ui.label_text(r)}",
                icon=folium.DivIcon(
                    html=(f'<div style="transform:translate(-50%,-50%);text-align:center;">'
                          f'<div style="display:inline-block;background:{color};color:white;'
                          f'border-radius:50%;width:24px;height:24px;line-height:24px;'
                          f'font-weight:bold;border:2px solid white;">{i + 1}</div>'
                          f'<div style="{pill}margin-top:2px;">{ui.esc(name)}</div>'
                          f'</div>'),
                    icon_size=(0, 0), icon_anchor=(0, 0)),
            ).add_to(m)
    user_marker(m, origin)
    m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
    return m


def layer_map(gdf, dark=False, limit=2000):
    """خريطة طبقة ناتجة عن تحليل، مع اسم كل معلم في التلميح."""
    g = gdf.head(limit).copy()
    labels = []
    cols = [c for c in ('name:ar', 'name', 'name:en') if c in g.columns]
    data = {c: g[c].tolist() for c in cols}
    for i in range(len(g)):
        nm = ui.row_name({c: data[c][i] for c in cols}, cols)
        labels.append(nm if nm else 'موقع')
    g['label'] = labels
    fields = ['label']
    aliases = ['الاسم']
    if 'count' in g.columns:
        fields.append('count')
        aliases.append('العدد')
    g = g[fields + ['geometry']]
    minx, miny, maxx, maxy = gdf.total_bounds
    m = base_map([(miny + maxy) / 2, (minx + maxx) / 2], 5, dark)
    folium.GeoJson(
        g,
        style_function=lambda f: {'color': '#0f766e', 'weight': 2, 'fillOpacity': 0.35},
        tooltip=folium.GeoJsonTooltip(fields=fields, aliases=aliases),
    ).add_to(m)
    m.fit_bounds([[miny, minx], [maxy, maxx]])
    return m


def trip_map(res, dark=False):
    """خريطة المشوار: المسار ثم محطات مرقّمة."""
    origin = res['origin']
    m = base_map(origin, 11, dark)
    line = res['line']
    folium.PolyLine(line, color='#9b2c22' if not dark else '#e3b07a', weight=6, opacity=0.85,
                    dash_array=None if not res.get('straight_only') else '8 6').add_to(m)
    lats, lons = [p[0] for p in line], [p[1] for p in line]
    for i, st_ in enumerate(res['stops'], 1):
        meta = ui.CAT.get(st_['key'], {})
        col = meta.get('color', '#9b2c22')
        name = ui.display_name(st_['name'], st_['key'])
        folium.Marker(
            [st_['lat'], st_['lon']], tooltip=f"{i}. {name}",
            icon=folium.DivIcon(
                html=(f'<div style="transform:translate(-50%,-50%);text-align:center;">'
                      f'<div style="display:inline-block;background:{col};color:#fff;border-radius:50%;'
                      f'width:30px;height:30px;line-height:30px;font-weight:700;border:2px solid #fff;'
                      f'box-shadow:0 1px 5px rgba(0,0,0,.5)">{i}</div>'
                      f'<div style="{_pill(dark)}margin-top:2px;">{ui.esc(name)}</div></div>'),
                icon_size=(0, 0), icon_anchor=(0, 0))).add_to(m)
    user_marker(m, origin)
    m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])
    return m


def gap_map(features, dark=False):
    m = base_map([24.0, 45.0], 5, dark)
    folium.GeoJson(
        {'type': 'FeatureCollection', 'features': features},
        style_function=lambda f: {'fillColor': f['properties']['color'], 'color': f['properties']['color'],
                                  'weight': 0, 'fillOpacity': 0.55},
        tooltip=folium.GeoJsonTooltip(fields=['km'], aliases=['أقرب مرفق (كم):']),
    ).add_to(m)
    return m