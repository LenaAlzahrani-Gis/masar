import geopandas as gpd
import pandas as pd
import requests
from pyogrio import list_layers
from shapely.geometry import Point

GPKG = 'data/city.gpkg'
LAYERS = {}
LAST_LAYER = None
ROUTE_GEOMS = {}
OSRM = 'https://router.project-osrm.org'
HEADERS = {'User-Agent': 'gis-agent-portfolio/1.0'}


def load_base_layers():
    for name, _ in list_layers(GPKG):
        gdf = gpd.read_file(GPKG, layer=name).to_crs(4326)
        gdf['geometry'] = gdf.geometry.make_valid()
        LAYERS[str(name)] = gdf


def _get(name):
    if name not in LAYERS:
        raise ValueError(f'layer {name} not found. Available: {list(LAYERS)}')
    return LAYERS[name]


def _save(name, gdf):
    global LAST_LAYER
    LAYERS[name] = gdf.to_crs(4326)
    LAST_LAYER = name
    return f'created layer {name} with {len(gdf)} features'


def _metric(gdf):
    return gdf.to_crs(gdf.estimate_utm_crs())


def _label(row):
    for c in ('name:ar', 'name', 'name:en'):
        v = row.get(c)
        if v is not None and not pd.isna(v) and str(v).strip():
            return str(v)
    return 'بدون اسم'


def _osrm_table(origin, dests):
    coords = ';'.join(f'{lon},{lat}' for lat, lon in [origin] + dests)
    r = requests.get(f'{OSRM}/table/v1/driving/{coords}',
                     params={'sources': 0, 'annotations': 'duration,distance'},
                     headers=HEADERS, timeout=15)
    r.raise_for_status()
    j = r.json()
    if j.get('code') != 'Ok':
        raise ValueError(j.get('code'))
    return j['durations'][0][1:], j['distances'][0][1:]


def _osrm_route(origin, dest):
    coords = f'{origin[1]},{origin[0]};{dest[1]},{dest[0]}'
    r = requests.get(f'{OSRM}/route/v1/driving/{coords}',
                     params={'overview': 'simplified', 'geometries': 'geojson'},
                     headers=HEADERS, timeout=15)
    r.raise_for_status()
    j = r.json()
    if j.get('code') != 'Ok':
        raise ValueError(j.get('code'))
    return [[lat, lon] for lon, lat in j['routes'][0]['geometry']['coordinates']]


def layers_info():
    out = []
    for n, g in LAYERS.items():
        gtype = str(g.geom_type.iloc[0]) if len(g) else 'empty'
        names = [c for c in ('name', 'name:ar', 'name:en') if c in g.columns]
        out.append({'name': n, 'type': gtype, 'count': len(g), 'name_columns': names})
    return out


def buffer_layer(layer, distance_m, output):
    g = _metric(_get(layer))
    g['geometry'] = g.geometry.buffer(distance_m)
    return _save(output, g)


def clip_layer(layer, clip_with, output):
    return _save(output, gpd.clip(_get(layer), _get(clip_with)))


def select_by_distance(layer, near_layer, max_distance_m, output):
    a = _metric(_get(layer))
    b = _get(near_layer).to_crs(a.crs)
    b['geometry'] = b.geometry.buffer(max_distance_m)
    hit = gpd.sjoin(a, b[['geometry']], how='inner', predicate='intersects')
    return _save(output, a.loc[hit.index.unique()])


def count_in_polygons(points_layer, polygons_layer, output):
    pts = _get(points_layer)
    polys = _get(polygons_layer).copy()
    hit = gpd.sjoin(pts, polys[['geometry']], how='inner', predicate='intersects')
    counts = hit.groupby('index_right').size()
    polys['count'] = polys.index.map(counts).fillna(0).astype(int)
    return _save(output, polys)


def summarize_layer(layer):
    g = _get(layer)
    if len(g) == 0:
        return {'count': 0}
    m = _metric(g)
    info = {'count': len(g)}
    gtype = g.geom_type.iloc[0]
    if gtype in ('Polygon', 'MultiPolygon'):
        info['total_area_km2'] = float(round(m.area.sum() / 1e6, 2))
    elif gtype in ('LineString', 'MultiLineString'):
        info['total_length_km'] = float(round(m.length.sum() / 1000, 2))
    if 'count' in g.columns:
        keep = [c for c in ('name', 'name:ar', 'name:en', 'count') if c in g.columns]
        top = g.sort_values('count', ascending=False).head(30)
        info['top5_by_count'] = top[keep].to_dict('records')
    return info


def nearest_to_point(layer, lat, lon, k, output):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('invalid coordinates')
    k = max(1, min(int(k), 5))
    g = _get(layer)
    g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
    if g.empty:
        raise ValueError(f'layer {layer} is empty')

    pt = gpd.GeoSeries([Point(lon, lat)], crs=4326)
    utm = pt.estimate_utm_crs()
    d = g.to_crs(utm).distance(pt.to_crs(utm).iloc[0])
    g['distance_km'] = (d / 1000).round(2)
    cand = g.sort_values('distance_km').head(max(k * 3, 8)).copy()
    pts = [r.geometry.representative_point() for _, r in cand.iterrows()]
    dests = [[p.y, p.x] for p in pts]
    cand['dlat'] = [x[0] for x in dests]
    cand['dlon'] = [x[1] for x in dests]

    mode = 'road'
    try:
        durs, dists = _osrm_table([lat, lon], dests)
        cand['minutes'] = [None if t is None else round(t / 60) for t in durs]
        cand['road_km'] = [None if x is None else round(x / 1000, 1) for x in dists]
        ranked = cand[cand['minutes'].notna()].sort_values('minutes')
        if ranked.empty:
            raise ValueError('no routes')
        top = ranked.head(k)
    except Exception:
        mode = 'straight_line'
        cand['minutes'] = None
        cand['road_km'] = None
        top = cand.head(k)

    geoms = []
    for _, row in top.iterrows():
        line = None
        if mode == 'road':
            try:
                line = _osrm_route([lat, lon], [row['dlat'], row['dlon']])
            except Exception:
                line = None
        geoms.append(line)
    ROUTE_GEOMS[layer] = geoms

    _save(output, top)
    results = []
    for _, row in top.iterrows():
        m, rk = row['minutes'], row['road_km']
        results.append({
            'name': _label(row),
            'straight_km': float(row['distance_km']),
            'road_km': None if pd.isna(rk) else float(rk),
            'minutes': None if pd.isna(m) else int(m),
            'lat': float(row['dlat']),
            'lon': float(row['dlon']),
        })
    return {'layer': layer, 'output_layer': output, 'routing': mode, 'results': results}


TOOL_FUNCS = {
    'layers_info': layers_info,
    'buffer_layer': buffer_layer,
    'clip_layer': clip_layer,
    'select_by_distance': select_by_distance,
    'count_in_polygons': count_in_polygons,
    'summarize_layer': summarize_layer,
    'nearest_to_point': nearest_to_point,
}


def _schema(name, desc, props):
    return {
        'name': name,
        'description': desc,
        'input_schema': {
            'type': 'object',
            'properties': {k: {'type': v[0], 'description': v[1]} for k, v in props.items()},
            'required': list(props),
        },
    }


L = ('string', 'input layer name')
OUT = ('string', 'name for the new output layer')

TOOL_SCHEMAS = [
    _schema('layers_info', 'List all layers with type, feature count and name columns.', {}),
    _schema('buffer_layer', 'Buffer every feature by distance_m meters.',
            {'layer': L, 'distance_m': ('number', 'distance in meters'), 'output': OUT}),
    _schema('clip_layer', 'Cut layer to the area of the polygon layer clip_with.',
            {'layer': L, 'clip_with': ('string', 'polygon layer name'), 'output': OUT}),
    _schema('select_by_distance', 'Keep features of layer within max_distance_m of any feature of near_layer.',
            {'layer': L, 'near_layer': ('string', 'layer to measure from'),
             'max_distance_m': ('number', 'distance in meters'), 'output': OUT}),
    _schema('count_in_polygons', 'Count features of points_layer inside each polygon of polygons_layer. Adds a count column.',
            {'points_layer': ('string', 'layer to count'), 'polygons_layer': ('string', 'polygon layer'), 'output': OUT}),
    _schema('summarize_layer', 'Return count, area or length, and top results.', {'layer': L}),
    _schema('nearest_to_point', 'Find the k nearest features (max 5) of a layer to a point (lat, lon), ranked by approximate driving time. Returns name, road_km and minutes (or straight_km only if routing is unavailable). Use for questions like where is the nearest hospital to me.',
            {'layer': L, 'lat': ('number', 'latitude of the point'), 'lon': ('number', 'longitude of the point'),
             'k': ('integer', 'how many nearest features to return, max 5'), 'output': OUT}),
]