import csv
import os
import time
import requests

URLS = ['https://overpass-api.de/api/interpreter',
        'https://overpass.private.coffee/api/interpreter',
        'https://maps.mail.ru/osm/tools/overpass/api/interpreter',
        'https://overpass.kumi.systems/api/interpreter']
TYPES = ['city', 'town', 'village']


def query(t):
    q = ('[out:json][timeout:180];area["ISO3166-1"="SA"]->.a;'
         f'node["place"="{t}"]["name"](area.a);out body;')
    for rnd in range(3):
        for u in URLS:
            try:
                r = requests.post(u, data={'data': q}, headers={'User-Agent': 'masar-gis/1.0'}, timeout=240)
                r.raise_for_status()
                return r.json()['elements']
            except Exception as e:
                print('  فشل', u.split('/')[2], str(e)[:40])
        print('  أعيد المحاولة بعد 20 ثانية...')
        time.sleep(20)
    return None


rows = []
for t in TYPES:
    print('جاري تنزيل:', t)
    els = query(t)
    if els is None:
        raise SystemExit('ما قدرت أنزل ' + t + '، جرّبي بعد شوي.')
    print('  تم', len(els))
    for e in els:
        tg = e.get('tags', {})
        rows.append([tg.get('name:ar') or tg.get('name', ''), tg.get('name:en', ''), e['lat'], e['lon'], t])

os.makedirs('data', exist_ok=True)
with open('data/places.csv', 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['name', 'name_en', 'lat', 'lon', 'place'])
    w.writerows(rows)
print('تم:', len(rows), 'موقع في data/places.csv')
