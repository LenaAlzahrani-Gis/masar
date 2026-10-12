import csv
import html
import io
import math
import urllib.parse

import extras

# (المفتاح، الاسم بالجمع، أيقونة، لون)
CATEGORIES = [
    ('hospitals', 'المستشفيات', 'local_hospital', '#dc2626'),
    ('clinics', 'العيادات', 'medical_services', '#0891b2'),
    ('pharmacies', 'الصيدليات', 'medication', '#16a34a'),
    ('doctors', 'الأطباء', 'stethoscope', '#0d9488'),
    ('police', 'الشرطة', 'local_police', '#2563eb'),
    ('civil_defense', 'الدفاع المدني', 'local_fire_department', '#ea580c'),
    ('schools', 'المدارس', 'school', '#7c3aed'),
    ('mosques', 'المساجد', 'mosque', '#15803d'),
    ('parks', 'الحدائق', 'park', '#65a30d'),
    ('restaurants', 'المطاعم', 'restaurant', '#db2777'),
    ('tourism', 'الأماكن السياحية', 'museum', '#d97706'),
    ('haramain', 'الحرمين الشريفين', 'kaaba', '#b8860b'),
    ('malls', 'المولات ومراكز التسوق', 'shopping_bag', '#c026d3'),
    ('supermarkets', 'السوبرماركت', 'shopping_cart', '#0ea5e9'),
    ('groceries', 'البقالات', 'storefront', '#f59e0b'),
    ('fuel', 'محطات الوقود', 'local_gas_station', '#475569'),
    ('train_stations', 'محطات القطار', 'train', '#0369a1'),
    ('railways', 'خطوط القطار', 'route', '#0f172a'),
    ('airports', 'المطارات', 'flight', '#4f46e5'),
    ('banks', 'البنوك', 'account_balance', '#0f766e'),
]

# تجميع الأيقونات فوق الخريطة (عنوان المجموعة، المفاتيح) بترتيب ثابت
GROUPS = [
    ('الخدمات', ['hospitals_all', 'clinics', 'pharmacies', 'police', 'civil_defense',
                 'schools', 'mosques', 'haramain', 'banks', 'parks']),
    ('التسوق والسياحة', ['tourism', 'malls', 'markets', 'restaurants']),
    ('النقل', ['fuel', 'rail', 'airports']),
]

# أيقونات مدمجة: المفتاح -> (الاسم، أيقونة، لون، الطبقات الفعلية)
MERGED = {
    'hospitals_all': ('المستشفيات والمراكز الطبية', 'local_hospital', '#dc2626', ['hospitals', 'doctors']),
    'markets': ('السوبرماركت والبقالات', 'shopping_cart', '#0ea5e9', ['supermarkets', 'groceries']),
    'rail': ('القطار: المحطات والخطوط', 'train', '#0369a1', ['train_stations', 'railways']),
}

LINE_LAYERS = {'railways'}

CAT = {k: {'label': lbl, 'icon': ic, 'color': col} for k, lbl, ic, col in CATEGORIES}
for _k, (_lbl, _ic, _col, _) in MERGED.items():
    CAT[_k] = {'label': _lbl, 'icon': _ic, 'color': _col}


def expand(keys):
    """يفكّ الأيقونات المدمجة إلى طبقاتها الفعلية دون تكرار."""
    out = []
    for k in keys:
        out += MERGED[k][3] if k in MERGED else [k]
    return list(dict.fromkeys(out))


def pill_available(key, layers):
    members = MERGED[key][3] if key in MERGED else [key]
    return any(m in layers for m in members)

AR_NAMES = {'regions': 'المناطق الإدارية', 'governorates': 'المحافظات'}
AR_NAMES.update({k: v['label'] for k, v in CAT.items() if k not in MERGED})

SINGULAR = {
    'hospitals': 'مستشفى', 'clinics': 'عيادة', 'pharmacies': 'صيدلية', 'doctors': 'مركز طبي',
    'police': 'مركز شرطة', 'civil_defense': 'مركز دفاع مدني', 'schools': 'مدرسة',
    'mosques': 'مسجد', 'parks': 'حديقة', 'restaurants': 'مطعم',
    'tourism': 'معلم سياحي', 'haramain': 'الحرم', 'malls': 'مركز تسوق', 'supermarkets': 'سوبرماركت',
    'groceries': 'بقالة', 'fuel': 'محطة وقود', 'train_stations': 'محطة قطار',
    'railways': 'خط قطار', 'airports': 'مطار', 'banks': 'بنك',
}

SUGGESTIONS = [
    ('hospitals', 'أقرب 3 مستشفيات', 'وين أقرب 3 مستشفيات لي؟'),
    ('police', 'أقرب مركز شرطة', 'وين أقرب مركز شرطة لي؟'),
    ('clinics', 'أقرب عيادة', 'وين أقرب عيادة لي؟'),
    ('pharmacies', 'أقرب صيدلية', 'وين أقرب صيدلية لي؟'),
    ('civil_defense', 'أقرب مركز دفاع مدني', 'وين أقرب مركز دفاع مدني لي؟'),
    ('restaurants', 'أقرب مطعم', 'وين أقرب مطعم لي؟'),
    ('parks', 'أقرب حديقة', 'وين أقرب حديقة لي؟'),
    ('schools', 'أقرب مدرسة', 'وين أقرب مدرسة لي؟'),
    ('mosques', 'أقرب مسجد', 'وين أقرب مسجد لي؟'),
    ('fuel', 'أقرب محطة وقود', 'وين أقرب محطة وقود لي؟'),
    ('tourism', 'أماكن سياحية قريبة', 'وين أقرب 5 أماكن سياحية لي؟'),
]

# هوية مسار: زمرد عميق + ذهب رملي (فاتح) / ليل زمردي + نعناعي + ذهبي (داكن)
LIGHT = {
    '--brand': '#5B3F8F', '--brand-soft': '#ECE4F5', '--brand-line': '#cfc3e3',
    '--on-brand': '#ffffff', '--ink': '#2B1E3F', '--muted': '#6a5d82', '--line': '#ddd3ea',
    '--bg': '#F5EEE2', '--card': '#FBF7EE', '--input': '#FFFDF8',
    '--accent2': '#C8922F', '--accent2-soft': '#F4E8C8',
    '--hero-a': '#2B1E3F', '--hero-b': '#2B1E3F',
    '--shadow': '0 1px 2px rgba(43,30,63,.08), 0 10px 26px -14px rgba(43,30,63,.30)',
}
DARK = {
    '--brand': '#B9A3DC', '--brand-soft': '#3a2c5a', '--brand-line': '#5a4a86',
    '--on-brand': '#2B1E3F', '--ink': '#F5EEE2', '--muted': '#b5a8cf', '--line': '#4A3B6E',
    '--bg': '#1E1630', '--card': '#2A2040', '--input': '#241a38',
    '--accent2': '#D9A848', '--accent2-soft': '#3a2c4e',
    '--hero-a': '#2A2040', '--hero-b': '#2A2040',
    '--shadow': '0 1px 2px rgba(0,0,0,.4), 0 12px 30px -16px rgba(0,0,0,.75)',
}

# مفتاح المظهر (شمس / قمر): متغيرات CSS تتغير بحسب الحالة
SWITCH_LIGHT = {
    '--sw-bg': 'linear-gradient(180deg,#4aa8ee,#b9e3ff)',
    '--sw-knob': 'radial-gradient(circle at 35% 35%,#ffe58a,#f4b02a)',
    '--sw-glow': '0 0 0 4px rgba(255,214,102,.35),0 0 16px #ffd36b',
    '--sw-x': '5px',
    '--sw-deco': ('radial-gradient(ellipse 14px 6px at 62% 70%,rgba(255,255,255,.95),transparent 70%),'
                  'radial-gradient(ellipse 18px 7px at 80% 52%,rgba(255,255,255,.85),transparent 70%)'),
}
SWITCH_DARK = {
    '--sw-bg': 'linear-gradient(180deg,#09112b,#223466)',
    '--sw-knob': ('radial-gradient(circle at 32% 38%,#aeb7cf 0 3px,transparent 4px),'
                  'radial-gradient(circle at 66% 66%,#aeb7cf 0 2.5px,transparent 3.5px),'
                  'radial-gradient(circle at 35% 35%,#f6f8fc,#c7cfe2)'),
    '--sw-glow': '0 0 0 4px rgba(200,210,255,.18),0 0 14px rgba(190,205,255,.55)',
    '--sw-x': '51px',
    '--sw-deco': ('radial-gradient(circle at 22% 30%,#fff 0 1px,transparent 1.6px),'
                  'radial-gradient(circle at 38% 68%,#fff 0 1.2px,transparent 1.8px),'
                  'radial-gradient(circle at 52% 24%,#dfe6ff 0 1px,transparent 1.6px),'
                  'radial-gradient(circle at 12% 62%,#dfe6ff 0 .9px,transparent 1.5px)'),
}


def esc(x):
    return html.escape(str(x))


def ms(name, cls=''):
    """أيقونة Material Symbols (مكتبة موحدة، بدون إيموجي)."""
    return f'<span class="ms {cls}">{name}</span>'


WX_ICON = {'☀️': 'wb_sunny', '⛅': 'partly_cloudy_day', '☁️': 'cloud', '🌫️': 'foggy', '🌦️': 'rainy_light',
           '🌧️': 'rainy', '❄️': 'ac_unit', '⛈️': 'thunderstorm', '🌡️': 'thermostat'}


def theme_vars(dark, accent=None):
    pal = dict(DARK if dark else LIGHT)
    pal.update(SWITCH_DARK if dark else SWITCH_LIGHT)
    pal['--accent'] = accent or pal['--brand']
    return ':root{' + ';'.join(f'{k}:{v}' for k, v in pal.items()) + '}'


def row_name(row, cols=('name:ar', 'name', 'name:en')):
    """أول اسم غير فارغ من الأعمدة المعطاة، أو None."""
    for c in cols:
        try:
            v = row.get(c)
        except Exception:
            v = None
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def display_name(name, layer):
    if name is None or str(name).strip() in ('', 'بدون اسم', 'nan', 'None'):
        return SINGULAR.get(layer, 'موقع')
    return str(name)


def label_text(r):
    if r.get('minutes') is not None:
        return f"≈ {r['minutes']} دقيقة · {r['road_km']} كم"
    return f"{r['straight_km']} كم (خط مباشر)"


def geom_kind(gtype):
    t = str(gtype)
    if 'Point' in t:
        return 'pt'
    if 'Line' in t:
        return 'ln'
    return 'pg'


def section_title(text):
    return f'<div class="side-title">{esc(text)}</div>'


def layer_rows_html(items, res=False):
    """items: قائمة (الاسم، العدد، النوع). ترقيم تسلسلي في اتجاه واحد."""
    out = ''
    for i, (label, count, kind) in enumerate(items, 1):
        out += (f'<div class="layer-row{" res" if res else ""}">'
                f'<span class="num">{i}</span>'
                f'<span class="nm"><span class="dot {kind}"></span>{esc(label)}</span>'
                f'<span class="ct">{count:,}</span></div>')
    return out


def result_cards_html(entries, colors):
    out = ''
    for e_i, e in enumerate(entries):
        color = colors[e_i % len(colors)]
        layer = e['result'].get('layer')
        icon = ms(CAT.get(layer, {}).get('icon', 'location_on'))
        results = e['result']['results']
        vals = [(r['minutes'] if r.get('minutes') is not None else r['straight_km']) for r in results]
        mx = max(vals) if vals and max(vals) else 1
        for i, r in enumerate(results, 1):
            name = display_name(r.get('name'), layer)
            if r.get('minutes') is not None:
                time_html = f"<b>{r['minutes']}</b> <span>دقيقة</span>"
                meta = f"{r['road_km']} كم بالسيارة تقريباً"
            else:
                time_html = f"<b>{r['straight_km']}</b> <span>كم</span>"
                meta = 'خط مباشر'
            pct = max(8, int(100 * vals[i - 1] / mx))
            out += (f'<div class="res-card"><div class="rank" style="background:{color}">{i}</div>'
                    f'<div class="res-body"><div class="res-name">{icon} {esc(name)}</div>'
                    f'<div class="res-meta">{esc(meta)}</div>'
                    f'<div class="res-bar"><span style="width:{pct}%;background:{color}"></span></div></div>'
                    f'<div class="res-time">{time_html}</div></div>')
    return out


def nearby_html(blocks):
    """blocks: قائمة (عنوان، [(الاسم، المسافة كم)]). ترتيب تصاعدي بالمسافة."""
    out = '<div class="near-grid">'
    for title, rows in blocks:
        out += f'<div class="near-block"><div class="near-title">{esc(title)}</div>'
        for i, (name, km) in enumerate(rows, 1):
            out += (f'<div class="layer-row"><span class="num">{i}</span>'
                    f'<span class="nm">{esc(name)}</span>'
                    f'<span class="ct">{km:,.1f} كم</span></div>')
        out += '</div>'
    return out + '</div>'


def push_history(hist, entry, limit=10):
    """يضيف النتيجة الجديدة في أول القائمة ويحتفظ بآخر limit نتائج."""
    return ([entry] + list(hist))[:limit]


def history_label(i, entry, width=30):
    req = entry['req']
    if len(req) > width:
        req = req[:width - 1] + '…'
    return f"{i}. {req}  ·  {entry['time']}"


# ---------------------------------------------------------------- الهوية والرأس
# ---------------------------------------------------------------- الشعار (وردة الاتجاهات والخزامى)

def b_sprig(color, rot=0, scale=1.0, w=1.0):
    t = f'rotate({rot} 100 100) translate(100 100) scale({scale}) translate(-100 -100)'
    el = ''.join(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" transform="rotate({r} {cx} {cy})"/>' for cx,cy,rx,ry,r in
        [(96.5,70,3.4,5,-25),(103.5,64,3.4,5,25),(96.8,57,3.1,4.6,-25),(103.2,51,3,4.4,25),(97.2,45,2.7,4,-22),(100,38,2.4,3.8,0)])
    return (f'<g transform="{t}" fill="{color}" stroke="none">{el}'
            f'<path d="M100 96 L100 40" stroke="{color}" stroke-width="2.6" stroke-linecap="round" fill="none"/></g>')

def b_ring_svg(color='#B9A3DC'):
    tri = ''.join(f'<path d="M96.8 19 L103.2 19 L100 12.5 Z" transform="rotate({a} 100 100)"/>' for a in range(0,360,15))
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">'
            f'<circle cx="100" cy="100" r="92" fill="none" stroke="{color}" stroke-width="1.6"/>'
            f'<circle cx="100" cy="100" r="80" fill="none" stroke="{color}" stroke-width="1.6"/>'
            f'<g fill="{color}">{tri}</g></svg>')

def b_rose_svg(dark=True):
    soft = '#B9A3DC'; main = '#E2D6F2' if dark else '#5B3F8F'; gold = '#D9A848'; core = '#2B1E3F' if dark else '#F5EEE2'
    gl = (f'<g fill="none" stroke="{soft}" stroke-width="1" opacity=".55"><circle cx="100" cy="100" r="70"/>'
          '<ellipse cx="100" cy="100" rx="35" ry="70"/><path d="M100 30 L100 170 M30 100 L170 100 M39.4 65 L160.6 65 M39.4 135 L160.6 135"/></g>')
    sq = (f'<g fill="none" stroke="{gold}" stroke-width="1.4"><rect x="55" y="55" width="90" height="90"/>'
          '<rect x="55" y="55" width="90" height="90" transform="rotate(45 100 100)"/></g>')
    sp = ''.join(b_sprig(soft, a, .68) for a in (45,135,225,315)) + ''.join(b_sprig(main, a) for a in (90,180,270)) + b_sprig(gold)
    ctr = (f'<circle cx="100" cy="100" r="10" fill="{core}" stroke="{main}" stroke-width="3"/>'
           f'<circle cx="100" cy="100" r="3.6" fill="{gold}"/>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200">{gl}{sq}{sp}{ctr}</svg>'

def b_mark_svg(size=None, cls=''):
    a = f' width="{size}" height="{size}"' if size else ''
    c = f' class="{cls}"' if cls else ''
    return (f'<svg{c}{a} viewBox="22 22 156 156" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
            '<rect x="50" y="50" width="100" height="100" fill="none" stroke="#B9A3DC" stroke-width="6"/>'
            '<rect x="50" y="50" width="100" height="100" fill="none" stroke="#B9A3DC" stroke-width="6" transform="rotate(45 100 100)"/>'
            '<path d="M100 100 L100 30" stroke="#D9A848" stroke-width="13" stroke-linecap="round"/>'
            '<path d="M100 100 L100 170 M100 100 L30 100 M100 100 L170 100" stroke="#F5EEE2" stroke-width="13" stroke-linecap="round"/>'
            '<circle cx="100" cy="100" r="15" fill="#5B3F8F" stroke="#F5EEE2" stroke-width="7"/></svg>')

def b_sadu_svg():
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="34" viewBox="0 0 40 34">'
            '<rect width="40" height="34" fill="#5B3F8F"/><rect width="40" height="4" fill="#2B1E3F"/><rect y="30" width="40" height="4" fill="#2B1E3F"/>'
            '<path d="M0 17 L10 7 L20 17 L10 27 Z" fill="#F5EEE2"/><path d="M5 17 L10 12 L15 17 L10 22 Z" fill="#5B3F8F"/>'
            '<path d="M20 30 L30 10 L40 30 Z" fill="#2B1E3F"/><path d="M26 30 L30 22 L34 30 Z" fill="#D9A848"/></svg>')

def b_uri(svg):
    return 'data:image/svg+xml,' + urllib.parse.quote(svg, safe="/:=,()")


LOGO_SVG = b_mark_svg(72, 'logo')

SADU = ('<div class="sadu"></div>')


def greeting_ar(hour):
    """ترحيب بلهجة سعودية بحسب الوقت (صياغة محايدة)."""
    if 5 <= hour < 11:
        head = 'صباح الخير، يا هلا ومرحبا في مسار'
    elif 11 <= hour < 15:
        head = 'يا هلا والله ومرحبا بك في مسار'
    elif 15 <= hour < 19:
        head = 'مساك الله بالخير، يا هلا ومرحبا'
    else:
        head = 'مساء الخير والسرور، يا هلا ومرحبا'
    sub = 'سمّ، وين وجهتك؟ اسأل مسار بالكتابة أو بالصوت، أو اختر من قائمة الأماكن.'
    return head, sub


def hero_html(loc, hour):
    head, sub = greeting_ar(hour)
    loc_chip = ('<span class="chip ok">● الموقع محدد</span>' if loc
                else '<span class="chip">○ الموقع غير محدد</span>')
    return ('<div class="hero"><div class="hero-brand">' + LOGO_SVG +
            '<div class="hero-id"><div class="wordmark">مسار</div>'
            '<div class="tagline">من سؤالك إلى وجهتك</div></div></div>'
            f'<div class="hero-hi"><div class="hi-t">{esc(head)}</div><div class="hi-x">{esc(sub)}</div></div>'
            f'<div class="chips">{loc_chip}<span class="chip ok">● مسار جاهز</span></div></div>')


def side_brand_html():
    return ('<div class="side-brand">' + LOGO_SVG.replace('width="72" height="72"', 'width="38" height="38"') +
            '<div><b>مسار</b><span>لوحتك الشخصية</span></div></div>')


def statusbar_html(loc, n_hist):
    return ('<div class="statusbar"><span class="ok">● مسار جاهز</span>'
            f'<span>الموقع: {"محدد" if loc else "غير محدد"}</span>'
            f'<span>نتائج محفوظة: {n_hist}</span><span class="grow"></span>'
            '<span>خرائط © مساهمو OpenStreetMap</span></div>')


# ---------------------------------------------------------------- بطاقات المعلومات
def ring_svg(score, size=64):
    r = 26
    c = 2 * math.pi * r
    off = c * (1 - score / 100)
    color = ('#16a34a' if score >= 80 else '#84cc16' if score >= 60
             else '#f59e0b' if score >= 40 else '#dc2626')
    return (f'<svg class="ring" width="{size}" height="{size}" viewBox="0 0 64 64">'
            f'<circle cx="32" cy="32" r="{r}" fill="none" stroke="var(--line)" stroke-width="7"/>'
            f'<circle cx="32" cy="32" r="{r}" fill="none" stroke="{color}" stroke-width="7" '
            f'stroke-linecap="round" stroke-dasharray="{c:.1f}" stroke-dashoffset="{off:.1f}" '
            f'transform="rotate(-90 32 32)"/>'
            f'<text x="32" y="38" text-anchor="middle" font-size="19" font-weight="700" '
            f'fill="var(--ink)">{score}</text></svg>')


def info_strip_html(weather, prayer, qibla_deg, access):
    cards = ''
    if weather:
        cards += (f'<div class="icard"><div class="ic-ic">{ms(WX_ICON.get(weather["icon"], "partly_cloudy_day"))}</div><div class="ic-body">'
                  f'<div class="ic-big">{weather["temp"]:.0f}°</div>'
                  f'<div class="ic-sub">{esc(weather["desc"])} · المحسوسة {weather["feels"]:.0f}° · '
                  f'رطوبة {weather["humidity"]:.0f}%</div></div></div>')
    if prayer:
        name, tm, mins = prayer
        cards += (f'<div class="icard"><div class="ic-ic">{ms("mosque")}</div><div class="ic-body">'
                  f'<div class="ic-big">{esc(name)} {esc(tm)}</div>'
                  f'<div class="ic-sub">{esc(extras.remaining_text(mins))}</div></div></div>')
    if access:
        cards += (f'<div class="icard">{ring_svg(access["score"], 52)}<div class="ic-body">'
                  f'<div class="ic-big">درجة الوصول: {esc(access["label"])}</div>'
                  f'<div class="ic-sub">من أصل 100 حول موقعك</div></div></div>')
    if qibla_deg is not None:
        cards += (f'<div class="icard"><div class="q-dial"><span class="q-n">N</span>'
                  f'<div class="q-arrow" style="transform:rotate({qibla_deg:.0f}deg)"></div></div>'
                  f'<div class="ic-body"><div class="ic-big">القبلة</div>'
                  f'<div class="ic-sub">{esc(extras.compass_ar(qibla_deg))} · {qibla_deg:.0f}°</div></div></div>')
    return f'<div class="info-strip">{cards}</div>' if cards else ''


def advice_card_html(adv, blocks):
    items = ''
    for title, rows in blocks:
        if rows:
            name, km = rows[0]
            items += (f'<span class="adv-pick"><b>{esc(title)}</b>: {esc(name)} · {km:,.1f} كم</span>')
    return (f'<div class="advice"><div class="adv-t">اقتراح حسب الجو</div>'
            f'<div class="adv-x">{esc(adv["text"])}</div>'
            f'<div class="adv-picks">{items}</div></div>')


def _acc_color(pct):
    return '#16a34a' if pct >= 80 else '#84cc16' if pct >= 60 else '#f59e0b' if pct >= 40 else '#dc2626'


def access_head_html(report):
    sc = report['score']
    return (f'<div class="acc-head">{ring_svg(sc, 110)}<div><div class="acc-label">{esc(report["label"])}</div>'
            f'<div class="acc-note">تقدير تقريبي مبني على مسافة الخط المباشر وعدد الخدمات '
            f'القريبة من موقعك. اضغط «اعرضه على الخريطة» لترى أقرب مكان من كل خدمة.</div></div></div>')


def access_row_html(r):
    meta = CAT.get(r['key'], {})
    pct = int(100 * r['sub'])
    nm = display_name(r['name'], r['key'])
    return (f'<div class="acc-row"><div class="acc-top"><span>{ms(meta.get("icon", "location_on"))} '
            f'{esc(meta.get("label", r["key"]))}</span>'
            f'<span class="acc-km">{r["nearest_km"]:,.1f} كم</span></div>'
            f'<div class="acc-bar"><span style="width:{max(pct, 4)}%;background:{_acc_color(pct)}"></span></div>'
            f'<div class="acc-sub">الأقرب: {esc(nm)} · {r["count"]} ضمن {r["radius"]:g} كم</div></div>')


def focus_html(f):
    meta = CAT.get(f['key'], {})
    return (f'<div class="focus-card"><div class="fc-ic">{ms(meta.get("icon", "location_on"))}</div><div>'
            f'<div class="fc-t">{esc(display_name(f["name"], f["key"]))}</div>'
            f'<div class="fc-m">{esc(meta.get("label", ""))} · يبعد عنك {f["km"]:,.1f} كم (خط مباشر)</div>'
            f'</div></div>')


# ---------------------------------------------------------------- اللوحة الجانبية
def t12(hhmm):
    h, m = map(int, hhmm.split(':'))
    return f'{(h % 12) or 12}:{m:02d} {"ص" if h < 12 else "م"}'


def loc_card_html(loc, source, acc):
    if not loc:
        return (f'<div class="side-card"><div class="loc-row"><div class="loc-pin off">{ms("location_off")}</div><div>'
                '<b>الموقع غير محدد</b><div class="sc-m">اسمح للمتصفح بالوصول إلى موقعك أو حدده يدوياً.</div>'
                '</div></div></div>')
    how = 'تم تحديده تلقائياً' if source == 'auto' else 'تم تحديده يدوياً'
    if source == 'auto' and acc:
        how += f' · دقة تقريبية {int(acc):,} م'
    return (f'<div class="side-card"><div class="loc-row"><div class="loc-pin">{ms("my_location")}</div><div>'
            f'<b>موقعك الحالي</b><div class="sc-m">{esc(how)}</div></div></div></div>')


def prayer_table_html(today, nxt_name, mins):
    rows = ''
    for key, name in extras.PRAYERS:
        now = ' now' if name == nxt_name else ''
        rows += f'<div class="pr-row{now}"><span>{esc(name)}</span><b>{esc(t12(today[key]))}</b></div>'
    note = (f'<div class="sc-m">الصلاة القادمة: {esc(nxt_name)} {esc(extras.remaining_text(mins))}</div>'
            if nxt_name else '')
    return f'<div class="side-card"><div class="sc-h">مواقيت الصلاة اليوم</div>{rows}{note}</div>'


def uv_text(v):
    return ('منخفضة' if v < 3 else 'متوسطة' if v < 6 else 'مرتفعة' if v < 8
            else 'مرتفعة جداً' if v < 11 else 'شديدة')


def weather_side_html(w):
    return ('<div class="side-card"><div class="sc-h">الطقس اليوم</div><div class="wx-grid">'
            f'<div><span>العظمى</span><b>{w["tmax"]:.0f}°</b></div>'
            f'<div><span>الصغرى</span><b>{w["tmin"]:.0f}°</b></div>'
            f'<div><span>الرياح</span><b>{w["wind"]:.0f} كم/س</b></div>'
            f'<div><span>الأشعة فوق البنفسجية</span><b>{uv_text(w["uv"])}</b></div>'
            '</div></div>')


def gap_legend_html():
    items = ''.join(f'<span class="lg"><i style="background:{c}"></i>{esc(t)}</span>'
                    for _, c, t in extras.GAP_LEGEND)
    return f'<div class="legend">{items}</div>'


def trip_html(res):
    if res.get('error'):
        return f'<div class="advice"><div class="adv-x">{esc(res["error"])}</div></div>'
    steps = '<div class="trip-step"><span class="tdot start"></span><div><b>موقعك</b></div></div>'
    for i, s in enumerate(res['stops'], 1):
        meta = CAT.get(s['key'], {})
        steps += (f'<div class="trip-step"><span class="tdot" style="background:{meta.get("color", "#5B3F8F")}">'
                  f'{i}</span><div><b>{esc(display_name(s["name"], s["key"]))}</b>'
                  f'<div class="res-meta">{esc(meta.get("label", ""))}</div></div></div>')
    if res.get('minutes') is not None:
        total = f'≈ {res["minutes"]} دقيقة · {res["km"]} كم بالسيارة'
    else:
        total = f'{res["km"]} كم (خط مباشر، تعذّر حساب المسار)'
    note = '<div class="res-meta">تم إعادة ترتيب المحطات لتقليل المسافة.</div>' if res.get('reordered') else ''
    return (f'<div class="trip-total">{esc(total)}</div>{note}<div class="trip-steps">{steps}</div>')


def place_card_html(info, item, thumb):
    img = ''
    if thumb and thumb.get('src'):
        cap = 'صورة توضيحية عامة (ليست للمكان نفسه)' if thumb.get('general') else 'صورة المكان'
        site = thumb.get('site') or 'ويكيبيديا'
        src = f'المصدر: <a href="{esc(thumb["page"])}" target="_blank">{site}</a>' if thumb.get('page') else f'المصدر: {site}'
        img = (f'<div class="pc-img"><img src="{esc(thumb["src"])}" alt="{esc(info["title"])}" loading="lazy">'
               f'<div class="pc-cap">{cap} · {src}</div></div>')
    if not img:
        img = '<div class="pc-img"><div class="pc-none">لا توجد صورة متاحة لهذا المكان حالياً</div></div>'
    meta = CAT.get(item['key'], {})
    return (f'<div class="place-card">{img}<div class="pc-body"><div class="pc-t">'
            f'{esc(display_name(info["title"], item["key"]))}</div>'
            f'<div class="pc-m">{esc(info["type"])} · يبعد عنك {item["km"]:,.1f} كم (خط مباشر)</div>'
            f'<div class="pc-x">{esc(info["blurb"])}</div></div></div>')


# ---------------------------------------------------------------- الدليل
GUIDE_STEPS = [
    ('my_location', 'حدد موقعك', 'اسمح للمتصفح بالوصول إلى الموقع، أو عدّله من اللوحة الجانبية.'),
    ('search', 'اسأل مسار', 'اكتب مثل: وين أقرب مستشفى لي؟ ويطلع لك الأقرب مع الزمن التقريبي.'),
    ('tune', 'التصنيفات', 'فعّل ما تحتاجه (مستشفيات، سياحة، وقود، قطارات...) وتظهر على الخريطة وفي قائمة الأقرب.'),
    ('near_me', 'اعرضه على الخريطة', 'اضغط زر الموقع بجانب أي نتيجة لتراه على الخريطة مع المسافة.'),
    ('target', 'درجة الوصول', 'تعرف قرب الخدمات منك، واضغط على أي خدمة لترى أقرب مكان لها.'),
    ('route', 'خطط مشوارك', 'اكتب مشوارك بجملة واحدة ويرتّب مسار المحطات لك.'),
]


def guide_html():
    steps = ''.join(
        f'<div class="g-step"><div class="g-ic">{ms(ic)}</div><div><b>{esc(t)}</b><span>{esc(d)}</span></div></div>'
        for ic, t, d in GUIDE_STEPS)
    return f'<div class="guide"><div class="guide-title">جولة سريعة في مسار</div><div class="guide-grid">{steps}</div></div>'


# ---------------------------------------------------------------- التصدير
def nearest_csv(entries):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['الترتيب', 'الاسم', 'الزمن التقريبي (دقيقة)', 'المسافة بالسيارة (كم)', 'المسافة المباشرة (كم)'])
    for e in entries:
        layer = e['result'].get('layer')
        for i, r in enumerate(e['result']['results'], 1):
            w.writerow([i, display_name(r.get('name'), layer), r.get('minutes', ''),
                        r.get('road_km', ''), r.get('straight_km', '')])
    return ('﻿' + buf.getvalue()).encode('utf-8')


def report_html(entry, map_html):
    rows = ''
    for s in entry['log']:
        if s['tool'] == 'nearest_to_point' and isinstance(s['result'], dict):
            layer = s['result'].get('layer')
            for i, r in enumerate(s['result']['results'], 1):
                rows += (f'<tr><td>{i}</td><td>{esc(display_name(r.get("name"), layer))}</td>'
                         f'<td>{esc(label_text(r))}</td></tr>')
    return ('<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<title>تقرير مسار</title><style>body{font-family:Tahoma,Segoe UI,sans-serif;max-width:900px;'
            'margin:24px auto;padding:0 16px;color:#14202b}h1{color:#5B3F8F}table{width:100%;'
            'border-collapse:collapse}td,th{border:1px solid #e4dccd;padding:8px;text-align:right}'
            'th{background:#e3f3ef}iframe{width:100%;height:480px;border:1px solid #e4dccd;'
            'border-radius:10px}.m{color:#5f6f7e;font-size:13px}</style></head><body>'
            f'<h1>مسار · تقرير</h1><p class="m">{esc(entry["req"])} · {esc(entry["time"])}</p>'
            f'<p>{esc(entry["text"])}</p>'
            f'<table><tr><th>#</th><th>الاسم</th><th>الزمن والمسافة</th></tr>{rows}</table><br>'
            f'<iframe srcdoc="{html.escape(map_html, quote=True)}"></iframe>'
            '<p class="m">البيانات من OpenStreetMap. الأزمنة تقريبية بدون حالة المرور.</p></body></html>')


# ---------------------------------------------------------------- لوحة النتائج
def est_minutes(km):
    """تقدير تقريبي لزمن القيادة من المسافة المباشرة (بدون مرور)."""
    road = km * 1.3
    speed = 30 if road <= 6 else 50 if road <= 40 else 90
    return max(1, round(road / speed * 60))


def fmt_minutes(m):
    if m < 60:
        return f'{m} د'
    h, r = divmod(m, 60)
    return f'{h} س و{r} د' if r else f'{h} س'


def panel_head_html(n, title='الأقرب إليك'):
    return f'<div class="pn-head"><b>{esc(title)}</b><span class="badge">{n}</span></div>'


def panel_row_html(it, selected=False):
    meta = CAT.get(it['key'], {})
    mins = it.get('minutes')
    approx = it.get('approx', False)
    t = fmt_minutes(mins) if mins is not None else ''
    sub = f'{"≈ " if approx else ""}{t}' if t else ''
    return (f'<div class="pn-row{" sel" if selected else ""}">'
            f'<span class="pn-ic" style="--c:{meta.get("color", "#5B3F8F")}">{ms(meta.get("icon", "location_on"))}</span>'
            f'<div class="pn-b"><div class="pn-t">{esc(display_name(it["name"], it["key"]))}</div>'
            f'<div class="pn-m">{esc(SINGULAR.get(it["key"], meta.get("label", "")))}</div></div>'
            f'<div class="pn-d"><b>{it["km"]:,.1f}</b> كم<span>{esc(sub)}</span></div></div>')


def panel_empty_html():
    return ('<div class="pn-empty">' + ms('travel_explore') +
            '<b>ابدأ من هنا</b><span>اسأل مسار في الأعلى، أو اختر تصنيفاً من الشريط وتظهر أقرب النتائج هنا.</span></div>')


def answer_html(entry, newest=True):
    tag = 'آخر بحث' if newest else 'نتيجة سابقة'
    return (f'<div class="answer"><div class="an-h">{ms("auto_awesome")}<b>{esc(tag)}</b>'
            f'<span>{esc(entry["req"])} · {esc(entry["time"])}</span></div>'
            f'<div class="an-x">{esc(entry["text"])}</div></div>')


def splash_html():
    """الافتتاحية: تُرسم في صفحة Streamlit نفسها (وليس داخل مكوّن الخريطة) فلا تتأثر بإعادة تحميله.
    الحركة كلها CSS ومدتها ثابتة: 5 ثوانٍ ثم تنزاح في 0.9 ثانية. بدون مسافات بادئة حتى لا يحوّلها markdown إلى كود."""
    ring, rose, sadu = b_uri(b_ring_svg('#B9A3DC')), b_uri(b_rose_svg(True)), b_uri(b_sadu_svg())
    css = (
        '@import url("https://fonts.googleapis.com/css2?family=El+Messiri:wght@700&family=IBM+Plex+Sans+Arabic:wght@500&display=swap");'
        '.mspl{position:fixed;inset:0;z-index:2147483000;background:#2B1E3F;display:grid;place-items:center;'
        'direction:rtl;pointer-events:all;animation:msOut .9s cubic-bezier(.7,0,.2,1) 5s forwards}'
        '@keyframes msOut{to{transform:translateY(-101%);visibility:hidden;pointer-events:none}}'
        '.mspl .in{display:flex;flex-direction:column;align-items:center;gap:10px}'
        '.mspl .lg{position:relative;width:min(230px,46vmin);height:min(230px,46vmin);margin-bottom:18px}'
        '.mspl .lg i{position:absolute;inset:0;background-size:contain;background-repeat:no-repeat;background-position:center}'
        f'.mspl .rg{{background-image:url("{ring}");opacity:0;animation:msF .9s ease .1s forwards,msSpin 70s linear .1s infinite}}'
        f'.mspl .rs{{background-image:url("{rose}");opacity:0;transform:scale(.55) rotate(-60deg);animation:msRose 1.1s cubic-bezier(.2,1.15,.4,1) .35s forwards}}'
        '.mspl .wd{font:700 clamp(54px,11vmin,120px)/1.05 "El Messiri","IBM Plex Sans Arabic",sans-serif;color:#F5EEE2;opacity:0;transform:translateY(14px);animation:msR .6s ease 1.3s forwards}'
        '.mspl .tg{font:500 clamp(14px,2.3vmin,24px) "IBM Plex Sans Arabic",sans-serif;color:#CFC2E3;opacity:0;transform:translateY(14px);animation:msR2 .6s ease 1.7s forwards}'
        '.mspl .wv{position:absolute;left:0;right:0;bottom:0;height:clamp(10px,2vmin,18px)}'
        f'.mspl .wv i{{display:block;height:100%;width:0;margin-inline-end:auto;background:url("{sadu}") repeat-x left center/auto 100%;'
        'animation:msW 1.6s cubic-bezier(.6,0,.3,1) .3s forwards}'
        '@keyframes msF{to{opacity:1}}'
        '@keyframes msSpin{to{transform:rotate(360deg)}}'
        '@keyframes msRose{to{opacity:1;transform:none}}'
        '@keyframes msR{to{opacity:1;transform:none}}'
        '@keyframes msR2{to{opacity:.9;transform:none}}'
        '@keyframes msW{to{width:100%}}'
        '.mspl .ld{display:flex;align-items:center;gap:8px;margin-top:14px;opacity:0;font:500 clamp(12px,1.9vmin,18px) "IBM Plex Sans Arabic",sans-serif;color:#F5EEE2;animation:msR2 .6s ease 2.6s forwards}'
        '.mspl .ld b{display:inline-block;width:7px;height:7px;border-radius:50%;background:#D9A848;animation:msD 1.1s ease-in-out infinite}'
        '.mspl .ld b:nth-of-type(2){animation-delay:.18s}.mspl .ld b:nth-of-type(3){animation-delay:.36s}'
        '@keyframes msD{0%,80%,100%{transform:scale(.5);opacity:.4}40%{transform:scale(1.15);opacity:1}}'
        'body:not(:has(iframe[title*="masar_ui"])):not(:has([data-testid="stException"])) .mspl{transform:none!important;visibility:visible!important;pointer-events:all!important}'
        'div[data-stale="true"]:has(.mspl){opacity:1!important}'
        '@media (prefers-reduced-motion:reduce){.mspl .rg{animation:msF .9s ease .1s forwards}}')
    html = ('<div class="mspl" aria-hidden="true"><div class="in"><div class="lg"><i class="rg"></i><i class="rs"></i></div>'
            '<div class="wd">مسار</div><div class="tg">من سؤالك إلى وجهتك</div>'
            '<div class="ld"><b></b><b></b><b></b><span>جارٍ تجهيز الخريطة</span></div></div><div class="wv"><i></i></div></div>')
    return f'<style>{css}</style>{html}'