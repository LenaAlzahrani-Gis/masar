import os
import time

import streamlit as st

import ui

st.set_page_config(page_title='مسار', page_icon=':material/explore:', layout='wide',
                   initial_sidebar_state='collapsed')

# ---------- الافتتاحية: تُرسم أول شي (قبل تحميل المكتبات الثقيلة) وتبقى 5 ثوانٍ ----------
_SPLASH_S = 5.9
_splash_t0 = st.session_state.setdefault('splash_t0', time.time())
_splash_left = max(0.0, _SPLASH_S - (time.time() - _splash_t0))
if time.time() - _splash_t0 < _SPLASH_S + 1.5:
    st.markdown(ui.splash_html(), unsafe_allow_html=True)

import csv
import io
from datetime import datetime, timedelta
from pathlib import Path

from pyogrio import list_layers
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation

import agent
import appdata
import component
import extras
import mapkit
import tools
import road
import trip

HERE = Path(__file__).parent

# المظهر: يتحدد تلقائياً بحسب الوقت عند أول فتح (داكن من 7 م إلى 5 ص)، ويبدّله مفتاح الشمس والقمر
if 'theme' not in st.session_state:
    _h = extras.now_ksa().hour
    st.session_state['theme'] = 'dark' if (_h >= 19 or _h < 5) else 'light'
DARK = st.session_state['theme'] == 'dark'

st.markdown(f"<style>{ui.theme_vars(DARK)}\n{(HERE / 'style.css').read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True)

# نحافظ على اختيارات الأدوات عند التنقل بين الأقسام
for _k in ('gap_key', 'gap_on'):
    if _k in st.session_state:
        st.session_state[_k] = st.session_state[_k]

if not tools.LAYERS:
    tools.load_base_layers()

DEFAULT_VIEW = {'center': [24.0, 45.0], 'zoom': 5}
DEV = st.query_params.get('dev') == '1'


# ---------- حد الاستخدام (يحمي رصيد المفتاح من الصرف الزائد) ----------
def _env_int(name, default):
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@st.cache_resource
def _quota():
    return {'day': None, 'n': 0}


def quota_take():
    """يحجز طلباً واحداً للذكاء الاصطناعي. يرجع None إذا مسموح، أو نص الرفض.
    الحدود: MASAR_MAX_PER_SESSION (افتراضي 10) و MASAR_MAX_PER_DAY (افتراضي 300).
    للتجربة المحلية بدون حد: MASAR_NO_LIMIT=1 (لا يعتمد على ?dev=1 حتى لا يتجاوزه الزوار)."""
    if os.getenv('MASAR_NO_LIMIT') == '1':
        return None
    per_session = _env_int('MASAR_MAX_PER_SESSION', 10)
    per_day = _env_int('MASAR_MAX_PER_DAY', 300)
    q = _quota()
    today = datetime.now().strftime('%Y-%m-%d')
    if q['day'] != today:
        q['day'], q['n'] = today, 0
    used = st.session_state.get('q_used', 0)
    if used >= per_session:
        return 'وصلت للحد المسموح من الأسئلة في هذه الجلسة. شكراً لتجربتك مسار!'
    if q['n'] >= per_day:
        return 'وصل مسار لحد الاستخدام اليومي. جرّب مرة ثانية بكرة.'
    q['n'] += 1
    st.session_state['q_used'] = used + 1
    return None


@st.cache_data
def base_layer_names():
    return [str(n) for n, _ in list_layers(tools.GPKG)]


@st.cache_data(ttl=600, show_spinner=False)
def get_weather(lat, lon):
    return extras.fetch_weather(lat, lon)


@st.cache_data(ttl=3600, show_spinner=False)
def get_prayer(lat, lon, day):
    return extras.fetch_prayer(lat, lon, day)


@st.cache_data(show_spinner=False)
def cached_gap(key, n, _gdf, _regions, _gov):
    feats, _ = extras.gap_grid(key, _gdf, _regions)
    table = extras.gov_table(key, _gdf, _gov) if _gov is not None else None
    return feats, table


def safe(fn, *args):
    try:
        return fn(*args)
    except Exception:
        return None


def queue(req):
    st.session_state['pending'] = req


def select_history(entry_id):
    st.session_state['active'] = entry_id


def toggle_theme():
    st.session_state['theme'] = 'light' if st.session_state.get('theme') == 'dark' else 'dark'


def focus_place(key, name, lat, lon, km):
    st.session_state['focus'] = {'key': key, 'name': name, 'lat': lat, 'lon': lon, 'km': float(km)}
    st.session_state['focus_n'] = st.session_state.get('focus_n', 0) + 1
    st.session_state['view'] = 'map'


def clear_focus():
    st.session_state.pop('focus', None)


def ensure_location():
    if st.session_state.get('loc_source') == 'manual':
        return
    data = get_geolocation()
    if not data:
        return
    if 'coords' in data:
        c = data['coords']
        new = [round(c['latitude'], 5), round(c['longitude'], 5)]
        if st.session_state.get('loc') != new:
            st.session_state['loc'] = new
            st.session_state['loc_source'] = 'auto'
            st.session_state['loc_acc'] = c.get('accuracy')
    else:
        st.session_state['loc_failed'] = True


def accuracy():
    if st.session_state.get('loc_source') == 'auto':
        return st.session_state.get('loc_acc')
    return None


def sidebar_panel(loc, hist, active_id, today, prayer, weather):
    sb = st.sidebar
    failed = st.session_state.get('loc_failed') and not loc
    sb.markdown(ui.side_brand_html(), unsafe_allow_html=True)

    # 1) الموقع
    sb.markdown(ui.loc_card_html(loc, st.session_state.get('loc_source'), st.session_state.get('loc_acc')),
                unsafe_allow_html=True)
    if failed:
        sb.warning('تعذّر تحديد الموقع تلقائياً. اسمح للمتصفح بالوصول إلى الموقع، أو حدده على الخريطة.')
    with sb.expander('تعديل موقعي', expanded=bool(failed)):
        view = st.session_state.get('picker_view')
        if not view:
            view = {'center': loc, 'zoom': 11} if loc else DEFAULT_VIEW
        m = mapkit.base_map(view['center'], view['zoom'], DARK)
        if loc:
            mapkit.user_marker(m, loc, accuracy())
        out = st_folium(m, height=260, use_container_width=True, key='picker',
                        returned_objects=['last_clicked', 'center', 'zoom'])
        if out:
            c, z = out.get('center'), out.get('zoom')
            if c and z:
                st.session_state['picker_view'] = {'center': [c['lat'], c['lng']], 'zoom': z}
            click = out.get('last_clicked')
            if click:
                new = [round(click['lat'], 5), round(click['lng'], 5)]
                if new != st.session_state.get('loc'):
                    st.session_state['loc'] = new
                    st.session_state['loc_source'] = 'manual'
                    st.rerun()

    # 2) الصلاة والطقس
    if today:
        sb.markdown(ui.prayer_table_html(today, prayer[0] if prayer else None, prayer[2] if prayer else 0),
                    unsafe_allow_html=True)
    if weather:
        sb.markdown(ui.weather_side_html(weather), unsafe_allow_html=True)
    if adv:
        akeys = [k for k in adv['keys'] if k in tools.LAYERS][:2]
        apicks = mapkit.nearby_list({k: tools.LAYERS[k] for k in akeys}, loc, n=1) if akeys else []
        sb.markdown(ui.advice_card_html(adv, apicks), unsafe_allow_html=True)

    # 3) نتائج البحث الأخيرة
    sb.markdown(ui.section_title('نتائج البحث الأخيرة'), unsafe_allow_html=True)
    if hist:
        for i, e in enumerate(hist, 1):
            sb.button(ui.history_label(i, e), key=f"h{e['id']}", on_click=select_history,
                      args=(e['id'],), use_container_width=True,
                      type='primary' if e['id'] == active_id else 'secondary')
    else:
        sb.caption('لا توجد عمليات بحث بعد. اسأل مسار وستظهر نتائجك هنا.')

    results = [n for n in tools.LAYERS if n not in base_layer_names()][-5:]
    if results:
        sb.markdown(ui.section_title('نتائج التحليل'), unsafe_allow_html=True)
        items = []
        for n in results:
            g = tools.LAYERS[n]
            kind = ui.geom_kind(g.geom_type.iloc[0]) if len(g) else 'pg'
            items.append((ui.AR_NAMES.get(n, n), len(g), kind))
        sb.markdown(ui.layer_rows_html(items, res=True), unsafe_allow_html=True)



def nearest_entries(entry):
    return [s for s in entry['log']
            if s['tool'] == 'nearest_to_point' and isinstance(s['result'], dict)]


def compose_map(entry, loc):
    rings = bool(st.session_state.get('rings'))
    if entry:
        nearest = nearest_entries(entry)
        if nearest:
            return mapkit.nearest_map(nearest, entry['geoms'], DARK)
        layer = entry['layer']
        if layer and layer in tools.LAYERS and len(tools.LAYERS[layer]) > 0:
            m = mapkit.layer_map(tools.LAYERS[layer], DARK)
            if loc:
                mapkit.user_marker(m, loc, accuracy(), rings)
            return m
    if loc:
        m = mapkit.base_map(loc, 13, DARK)
        mapkit.user_marker(m, loc, accuracy(), rings)
    else:
        m = mapkit.base_map(DEFAULT_VIEW['center'], DEFAULT_VIEW['zoom'], DARK)
    return m


# ---------- بيانات الموقع (الطقس والصلاة ودرجة الوصول) ----------
ensure_location()
loc = st.session_state.get('loc')

weather = adv = prayer = acc_report = today = None
qibla = None
if loc:
    la, lo = round(loc[0], 2), round(loc[1], 2)
    weather = safe(get_weather, la, lo)
    if weather:
        adv = extras.advice(weather)
    now = extras.now_ksa()
    today = safe(get_prayer, la, lo, now.strftime('%d-%m-%Y'))
    tomorrow = safe(get_prayer, la, lo, (now + timedelta(days=1)).strftime('%d-%m-%Y'))
    if today:
        prayer = extras.next_prayer(today, tomorrow, now)
    qibla = extras.qibla_bearing(loc[0], loc[1])
    acc_report = safe(extras.access_report, tools.LAYERS, loc)

# ---------- تنفيذ الطلب (قبل رسم اللوحة الجانبية ليظهر في السجل مباشرة) ----------
pending = st.session_state.pop('pending', None)
if pending:
    tools.LAST_LAYER = None
    tools.ROUTE_GEOMS.clear()
    note = ''
    if weather:
        note = (f"\n(للعلم فقط، استخدمها إذا كانت مفيدة للسؤال: الجو الآن عند المستخدم {weather['desc']} "
                f"والحرارة {weather['temp']:.0f} مئوية والمحسوسة {weather['feels']:.0f}.)")
    t0 = datetime.now()
    deny = quota_take()
    try:
        if deny:
            raise RuntimeError('quota')
        text, log = agent.run_agent(pending + note, location=st.session_state.get('loc'))
    except Exception as ex:
        st.session_state['notice'] = {'id': datetime.now().timestamp(),
                                      'text': deny or 'تعذّر تنفيذ الطلب. تحقق من الاتصال ومن رصيد المفتاح ثم حاول مرة أخرى.'}
        if DEV and not deny:
            st.exception(ex)
    else:
        n = st.session_state.get('hist_n', 0) + 1
        st.session_state['hist_n'] = n
        entry = {'id': n, 'req': pending, 'time': datetime.now().strftime('%H:%M'),
                 'text': text, 'log': log, 'layer': tools.LAST_LAYER, 'geoms': dict(tools.ROUTE_GEOMS),
                 'secs': round((datetime.now() - t0).total_seconds(), 1)}
        st.session_state['history'] = ui.push_history(st.session_state.get('history', []), entry)
        st.session_state['active'] = n

hist = st.session_state.get('history', [])
active_id = st.session_state.get('active')
entry = next((e for e in hist if e['id'] == active_id), None)

if 'view_req' in st.session_state:
    st.session_state['view'] = st.session_state.pop('view_req')
st.session_state.setdefault('view', 'map')
view = st.session_state.get('view') or 'map'

sidebar_panel(loc, hist, active_id, today if loc else None, prayer, weather)

if adv and extras.ACCENTS.get(adv['mood']):
    st.markdown(f"<style>:root{{--accent:{extras.ACCENTS[adv['mood']]}}}</style>", unsafe_allow_html=True)

if view != 'map':
    st.markdown('<style>html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"],section.main{overflow:auto!important;height:auto!important}</style>', unsafe_allow_html=True)
    # ---------- الرأس: الهوية + الترحيب + دليل الاستخدام + المظهر ----------
    with st.container(key='header'):
        h1, h2, h3 = st.columns([8, 2.4, 1.3], vertical_alignment='top')
        h1.markdown(ui.hero_html(loc, extras.now_ksa().hour), unsafe_allow_html=True)
        with h2:
            with st.container(key='guide_pop'):
                with st.popover(':material/help: دليل الاستخدام', use_container_width=True):
                    st.markdown(ui.guide_html(), unsafe_allow_html=True)
            st.button(':material/map: العودة إلى الخريطة', key='back_map',
                      on_click=lambda: st.session_state.update(view='map'), use_container_width=True)
        with h3:
            with st.container(key='theme_sw'):
                st.button('تبديل المظهر', key='theme_btn', on_click=toggle_theme,
                          help='الوضع الفاتح / الداكن', use_container_width=True)
    if loc:
        st.markdown(ui.info_strip_html(weather, prayer, qibla, acc_report), unsafe_allow_html=True)
else:
    st.markdown("""<style>
      html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"],section.main{overflow:hidden!important;height:100vh!important}
      [data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],[data-testid="stStatusWidget"],
      [data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="collapsedControl"],.statusbar{display:none!important}
      .block-container,[data-testid="stMainBlockContainer"]{padding:0!important;margin:0!important;max-width:100%!important}
      [data-testid="stVerticalBlock"]{gap:0!important}
      [data-stale="true"],[data-testid="stElementContainer"]:has(iframe[title*="masar_ui"]),iframe[title*="masar_ui"]{opacity:1!important;filter:none!important;transition:none!important}
      [data-testid="stStatusWidget"],[data-testid="stAppDeployButton"]{display:none!important}
      iframe[title*="streamlit_js_eval"]{position:fixed!important;width:0!important;height:0!important;opacity:0!important;pointer-events:none!important;border:0!important}
      [data-testid="stElementContainer"]:has(iframe[title*="streamlit_js_eval"]){position:fixed!important;width:0!important;height:0!important;overflow:hidden!important}
      html,body,.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:__BG__!important}
      iframe[data-testid="stCustomComponentV1"]:not([title*="streamlit_js_eval"]),iframe[title*="masar_ui"],[data-testid="stElementContainer"]:has(iframe[title*="masar_ui"]){
        position:fixed!important;top:0!important;left:0!important;right:0!important;bottom:0!important;
        width:100vw!important;height:100vh!important;border:0!important;margin:0!important;z-index:5}
    </style>""".replace('__BG__', '#171210' if DARK else '#e6dbc4'), unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def cached_cats(loc_key, sizes, _layers):
    return appdata.build_cats(_layers, list(loc_key) if loc_key else None)


# ======================= الخريطة والبحث =======================
if view == 'map':
    loc_key = (round(loc[0], 3), round(loc[1], 3)) if loc else None
    sizes = tuple((k, len(g)) for k, g in tools.LAYERS.items() if k in ui.CAT or k in ui.MERGED)
    cats = cached_cats(loc_key, sizes, tools.LAYERS)
    nearest = nearest_entries(entry) if entry else []
    answer = appdata.build_answer(entry, nearest, tools.LAYERS) if entry else None

    info = {}
    if weather:
        info['weather'] = {'temp': weather['temp'], 'desc': weather['desc'],
                           'icon': ui.WX_ICON.get(weather['icon'], 'partly_cloudy_day')}
    if prayer:
        info['prayer'] = {'name': prayer[0], 'time': ui.t12(prayer[1]), 'left': extras.remaining_text(prayer[2])}
    focus = st.session_state.get('focus')
    if focus:
        meta = ui.CAT.get(focus['key'], {})
        focus = dict(focus, icon=meta.get('icon', 'location_on'), color=meta.get('color', '#9b2c22'),
                     label=ui.SINGULAR.get(focus['key'], meta.get('label', '')))
    treq = st.session_state.pop('trip_req', None)
    if treq:
        t_layers = {k: tools.LAYERS[k] for k in trip.TRIP_LABELS if k in tools.LAYERS}
        if not loc:
            plan = {'error': 'حدد موقعك أولاً ليخطط مسار المشوار.'}
        elif not t_layers:
            plan = {'error': 'لا توجد بيانات كافية لتخطيط المشوار.'}
        elif (qd := quota_take()):
            plan = {'error': qd}
        else:
            try:
                plan = trip.make_plan(treq, loc, t_layers)
            except Exception as ex:
                plan = {'error': 'تعذّر تخطيط المشوار. تحقق من الاتصال ومن مفتاح الخدمة ثم حاول مرة أخرى.'}
                if DEV:
                    st.exception(ex)
        plan['id'] = datetime.now().timestamp()
        st.session_state['trip_plan'] = plan
    rreq = st.session_state.pop('road_req', None)
    if rreq:
        if 'fuel' not in tools.LAYERS:
            rplan = {'error': 'لا توجد بيانات كافية لفحص الرحلة.'}
        elif (qd := quota_take()):
            rplan = {'error': qd}
        else:
            try:
                rplan = road.make_plan(rreq['text'], loc, tools.LAYERS, rreq.get('range') or road.DEFAULT_RANGE)
            except Exception as ex:
                rplan = {'error': 'تعذّر فحص الرحلة. تحقق من الاتصال ومن مفتاح الخدمة ثم حاول مرة أخرى.'}
                if DEV:
                    st.exception(ex)
        rplan['id'] = datetime.now().timestamp()
        st.session_state['road_plan'] = rplan
    creq = st.session_state.pop('cmp_req', None)
    if creq:
        ra = safe(extras.access_report, tools.LAYERS, creq[0])
        rb = safe(extras.access_report, tools.LAYERS, creq[1])
        st.session_state['cmp_res'] = appdata.compare_payload(ra, rb, creq[0], creq[1],
                                                              datetime.now().timestamp())
    cmp_data = st.session_state.get('cmp_res')
    trip_data = appdata.trip_payload(st.session_state.get('trip_plan'))
    road_data = appdata.road_payload(st.session_state.get('road_plan'))
    data = {'dark': DARK, 'loc': loc, 'acc': accuracy(), 'cats': cats, 'answer': answer, 'info': info,
            'greeting': list(ui.greeting_ar(extras.now_ksa().hour)),
            'guide': [list(g) for g in ui.GUIDE_STEPS],
            'lstDate': (extras.now_ksa() - timedelta(days=3)).strftime('%Y-%m-%d'),
            'dev': DEV, 'focus': focus, 'focusId': st.session_state.get('focus_n', 0),
            'notice': st.session_state.get('notice'), 'trip': trip_data, 'road': road_data, 'compare': cmp_data,
            'hist': {'ids': [e['id'] for e in hist], 'active': active_id},
            'splash_ms': int(max(0.0, _SPLASH_S - (time.time() - _splash_t0)) * 1000)}
    ev = component.masar_ui(data, key='masar_ui')
    if ev and ev.get('nonce') != st.session_state.get('last_nonce'):
        st.session_state['last_nonce'] = ev.get('nonce')
        kind = ev.get('type')
        if kind == 'ask' and ev.get('text'):
            st.session_state['pending'] = str(ev['text'])[:500]
            st.rerun()
        elif kind == 'theme':
            st.session_state['theme'] = 'dark' if ev.get('dark') else 'light'
            st.rerun()
        elif kind == 'compare' and ev.get('a') and ev.get('b'):
            try:
                pa = [float(ev['a'][0]), float(ev['a'][1])]
                pb = [float(ev['b'][0]), float(ev['b'][1])]
                st.session_state['cmp_req'] = (pa, pb)
            except (TypeError, ValueError, IndexError):
                pass
            st.rerun()
        elif kind == 'trip' and ev.get('text'):
            st.session_state['trip_req'] = str(ev['text'])[:300]
            st.rerun()
        elif kind == 'road' and ev.get('text'):
            try:
                rg = float(ev.get('range') or 0)
            except (TypeError, ValueError):
                rg = 0
            st.session_state['road_req'] = {'text': str(ev['text'])[:300], 'range': rg or None}
            st.rerun()
        elif kind == 'hist' and ev.get('id') in [e['id'] for e in hist]:
            st.session_state['active'] = ev['id']
            st.rerun()
        elif kind == 'nav' and ev.get('view') in ('score', 'gap', 'trip'):
            st.session_state['view_req'] = ev['view']
            st.rerun()

# ======================= درجة الوصول =======================
if view == 'score':
    if not loc:
        st.info('حدد موقعك أولاً ليحسب مسار درجة الوصول.')
    elif not acc_report:
        st.info('لا توجد طبقات كافية لحساب الدرجة.')
    else:
        st.markdown(ui.access_head_html(acc_report), unsafe_allow_html=True)
        cols = st.columns(2)
        for i, r in enumerate(acc_report['rows']):
            with cols[i % 2]:
                with st.container(key=f'accrow_{i}'):
                    st.markdown(ui.access_row_html(r), unsafe_allow_html=True)
                    st.button(':material/near_me: اعرضه على الخريطة', key=f'acc_go_{i}', on_click=focus_place,
                              args=(r['key'], r['name'], r['lat'], r['lon'], r['nearest_km']),
                              use_container_width=True)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(['الخدمة', 'أقرب مرفق (كم)', 'العدد ضمن نصف القطر', 'نصف القطر (كم)', 'الدرجة الجزئية'])
        for r in acc_report['rows']:
            w.writerow([ui.CAT.get(r['key'], {}).get('label', r['key']), round(r['nearest_km'], 2),
                        r['count'], r['radius'], round(r['sub'], 2)])
        st.download_button('تنزيل تفاصيل الدرجة (CSV)', ('﻿' + buf.getvalue()).encode('utf-8'),
                           file_name='masar_access.csv', mime='text/csv')

# ======================= فجوات الخدمات =======================
if view == 'gap':
    gap_keys = [k for k in ('hospitals', 'clinics', 'pharmacies', 'police', 'civil_defense', 'schools',
                            'mosques', 'fuel', 'supermarkets', 'airports') if k in tools.LAYERS]
    if not gap_keys or 'regions' not in tools.LAYERS:
        st.info('لا توجد طبقات كافية لتحليل الفجوات.')
    else:
        st.caption('كل مربع على الخريطة يلوّن بعده عن أقرب مرفق من الخدمة المختارة (مسافة خط مباشر).')
        gk = st.selectbox('الخدمة', gap_keys, key='gap_key',
                          format_func=lambda k: ui.CAT[k]['label'])
        if st.toggle('عرض التحليل', key='gap_on'):
            try:
                with st.spinner('جاري حساب الفجوات...'):
                    feats, table = cached_gap(gk, len(tools.LAYERS[gk]), tools.LAYERS[gk],
                                              tools.LAYERS['regions'], tools.LAYERS.get('governorates'))
            except Exception as ex:
                st.error('تعذّر حساب التحليل.')
                if DEV:
                    st.exception(ex)
            else:
                st.markdown(ui.gap_legend_html(), unsafe_allow_html=True)
                st_folium(mapkit.finish(mapkit.gap_map(feats, DARK)), height=520, use_container_width=True,
                          key=f'gap_{gk}_{DARK}', returned_objects=[])
                if table is not None:
                    st.markdown(ui.section_title('المحافظات الأبعد عن الخدمة'), unsafe_allow_html=True)
                    st.dataframe(table.head(20), use_container_width=True, hide_index=True)
                    st.download_button('تنزيل الجدول كاملاً (CSV)',
                                       table.to_csv(index=False).encode('utf-8-sig'),
                                       file_name=f'masar_gaps_{gk}.csv', mime='text/csv')

# ======================= تخطيط مشوار =======================
if view == 'trip':
    trip_layers = {k: tools.LAYERS[k] for k in trip.TRIP_LABELS if k in tools.LAYERS}
    st.caption('اكتب مشوارك بجملة واحدة، مثل: أبغى أعبي بنزين وبعدها أروح المول وأصلي. '
               'يختار مسار أقرب المحطات ويرتبها ويحسب الوقت التقريبي.')
    with st.form('trip_form', border=False):
        t1, t2 = st.columns([6, 1])
        t_in = t1.text_input('مشوارك', label_visibility='collapsed',
                             placeholder='مثال: أبغى أعبي بنزين وبعدها أروح المول وأصلي')
        go = t2.form_submit_button('خطّط', use_container_width=True)
    if go and t_in:
        if not loc:
            st.warning('حدد موقعك أولاً.')
        elif not trip_layers:
            st.warning('لا توجد طبقات كافية لتخطيط المشوار.')
        else:
            try:
                with st.spinner('جاري ترتيب المشوار...'):
                    st.session_state['trip'] = trip.make_plan(t_in, loc, trip_layers)
            except Exception as ex:
                st.session_state['trip'] = {'error': 'تعذّر تخطيط المشوار. تحقق من الاتصال ومن مفتاح الخدمة ثم حاول مرة أخرى.'}
                if DEV:
                    st.exception(ex)
    plan = st.session_state.get('trip')
    if plan:
        st.markdown(ui.trip_html(plan), unsafe_allow_html=True)
        if not plan.get('error'):
            st_folium(mapkit.finish(mapkit.trip_map(plan, DARK)), height=500, use_container_width=True,
                      key=f"trip_{abs(hash((plan['text'], DARK)))}", returned_objects=[])

if DEV and entry:
    with st.expander('سجل الخطوات'):
        for step in entry['log']:
            st.write(step['tool'])
            st.json(step['args'])
            st.write(step['result'])

st.markdown(ui.statusbar_html(loc, len(hist)), unsafe_allow_html=True)