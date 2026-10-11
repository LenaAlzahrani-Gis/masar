"""مسار: فكرة قصيرة وصورة توضيحية عامة للأماكن (السياحة والحرمين والقطارات)."""
import requests

HEADERS = {'User-Agent': 'masar-portfolio/1.0'}
WIKI = 'https://en.wikipedia.org/api/rest_v1/page/summary/'

# قيمة الوسم في OSM -> (النوع، فكرة قصيرة عامة)
KIND_INFO = {
    'museum': ('متحف', 'مكان يعرض التراث والتاريخ والمقتنيات، ومناسب لزيارة هادئة وتعليمية.'),
    'viewpoint': ('إطلالة', 'نقطة مفتوحة لمشاهدة المناظر الطبيعية، والأجمل زيارتها وقت الغروب أو في الصباح الباكر.'),
    'attraction': ('معلم سياحي', 'موقع يقصده الزوار للتعرف على المكان والتصوير والاستمتاع.'),
    'theme_park': ('مدينة ملاهي', 'مكان ترفيهي للعائلات والأطفال، فيه ألعاب وفعاليات.'),
    'zoo': ('حديقة حيوان', 'مكان لمشاهدة الحيوانات، ومناسب للعائلات والأطفال.'),
    'aquarium': ('أكواريوم', 'مكان لمشاهدة الأحياء البحرية، ومناسب للعائلات.'),
    'gallery': ('معرض فني', 'مساحة تعرض أعمالاً فنية وإبداعية.'),
    'archaeological_site': ('موقع أثري', 'موقع يحمل آثاراً من حقب قديمة. يُفضّل زيارته نهاراً بملابس وأحذية مريحة.'),
    'castle': ('قلعة', 'مبنى تاريخي دفاعي يروي جانباً من تاريخ المنطقة.'),
    'fort': ('حصن', 'مبنى تاريخي دفاعي يروي جانباً من تاريخ المنطقة.'),
    'monument': ('نصب تذكاري', 'معلم يخلّد حدثاً أو شخصية أو مكاناً مهماً.'),
    'ruins': ('أطلال', 'بقايا مبانٍ قديمة تدلّ على حياة سابقة في المكان.'),
}
DEFAULT_KIND = ('معلم سياحي', 'موقع يقصده الزوار للتعرف على المكان والاستمتاع به.')

HARAM = {
    'title': 'المسجد الحرام', 'type': 'مسجد',
    'blurb': 'في مكة المكرمة، يحيط بالكعبة المشرفة وهو أقدس موقع في الإسلام وقبلة المسلمين. '
             'يقصده المعتمرون والحجاج طوال العام.',
    'wiki': 'Masjid_al-Haram',
    'cands': [('ar', 'المسجد_الحرام'), ('en', 'Masjid_al-Haram'), ('en', 'Great_Mosque_of_Mecca')],
}
NABAWI = {
    'title': 'المسجد النبوي', 'type': 'مسجد',
    'blurb': 'في المدينة المنورة، ثاني أقدس المساجد في الإسلام، ويضم القبر الشريف تحت القبة الخضراء. '
             'يزوره المسلمون طوال العام.',
    'wiki': "Prophet's_Mosque",
    'cands': [('ar', 'المسجد_النبوي'), ('en', "Prophet's_Mosque"), ('en', 'Al-Masjid_an-Nabawi')],
}
STATION = {
    'type': 'محطة قطار',
    'blurb': 'محطة ضمن شبكة القطارات في المملكة. من الشبكات: قطار الحرمين السريع بين مكة المكرمة وجدة '
             'والمدينة المنورة (يعمل بسرعة تصل إلى 300 كم/س تقريباً، وافتُتح للجمهور في أكتوبر 2018)، '
             'ومترو الرياض (6 مسارات و85 محطة، بدأ التشغيل في ديسمبر 2024).',
    'wiki': 'Haramain_High_Speed_Railway',
    'cands': [('en', 'Haramain_High_Speed_Railway'), ('ar', 'قطار_الحرمين_السريع')],
}
TOURISM_IMAGE = 'Diriyah'      # صورة توضيحية عامة للسياحة
TOURISM_CANDS = [('en', 'Diriyah'), ('en', 'Saudi_Arabia'), ('en', 'Riyadh')]


def describe(layer_key, name, kind=None, desc=None, wiki=None, wikidata=None, commons=None):
    """يرجع {'title','type','blurb','cands','general', ...} لعرض بطاقة المكان."""
    own = {'wikipedia': wiki, 'wikidata': wikidata, 'commons': commons}
    if layer_key == 'haramain':
        base = NABAWI if (name and 'النبوي' in name) else HARAM
        return {**base, 'general': False, 'own': {}, 'fallback': []}
    if layer_key == 'train_stations':
        return {'title': name, 'type': STATION['type'], 'blurb': STATION['blurb'], 'own': own,
                'fallback': STATION['cands'], 'general': True}
    typ, blurb = KIND_INFO.get(kind, DEFAULT_KIND)
    if desc:
        blurb = f'{blurb} وصف المكان على الخريطة: {desc}'
    return {'title': name, 'type': typ, 'blurb': blurb, 'own': own,
            'fallback': TOURISM_CANDS, 'general': True}


# ------------------------------------------------------------------ جلب الصور
def _get(url, **params):
    r = requests.get(url, params=params or None, headers=HEADERS, timeout=8)
    r.raise_for_status()
    return r.json()


def _summary(lang, title):
    """صورة ورابط صفحة من ويكيبيديا (لغة + عنوان). يرجع None إن لا صورة."""
    j = _get(f'https://{lang}.wikipedia.org/api/rest_v1/page/summary/'
             + requests.utils.quote(title.replace(' ', '_'), safe="_'(),"))
    src = (j.get('thumbnail') or {}).get('source')
    if not src:
        return None
    page = ((j.get('content_urls') or {}).get('desktop') or {}).get('page')
    return {'src': src, 'page': page, 'site': 'ويكيبيديا'}


def _commons_file(fname):
    fname = fname.split(':', 1)[1] if fname.lower().startswith('file:') else fname
    q = requests.utils.quote(fname.replace(' ', '_'))
    return {'src': f'https://commons.wikimedia.org/wiki/Special:FilePath/{q}?width=600',
            'page': f'https://commons.wikimedia.org/wiki/File:{q}', 'site': 'ويكيميديا كومنز'}


def _from_wikidata(qid):
    j = _get('https://www.wikidata.org/w/api.php', action='wbgetentities', ids=qid,
             props='claims|sitelinks', format='json')
    ent = (j.get('entities') or {}).get(qid) or {}
    p18 = (ent.get('claims') or {}).get('P18') or []
    if p18:
        try:
            return _commons_file(p18[0]['mainsnak']['datavalue']['value'])
        except (KeyError, TypeError):
            pass
    links = ent.get('sitelinks') or {}
    for site, lang in (('arwiki', 'ar'), ('enwiki', 'en')):
        if site in links:
            r = _summary(lang, links[site]['title'])
            if r:
                return r
    return None


def _geo_match(lat, lon, names):
    """أقرب مقال ويكيبيديا ضمن 250 م، ونقبله فقط إذا الاسم متشابه أو قريب جداً (60 م)."""
    for lang in ('ar', 'en'):
        j = _get(f'https://{lang}.wikipedia.org/w/api.php', action='query', list='geosearch',
                 gscoord=f'{lat}|{lon}', gsradius=250, gslimit=5, format='json')
        for g in (j.get('query') or {}).get('geosearch', []):
            t = g['title'].lower()
            ok = any(n and (n.lower() in t or t in n.lower()) for n in names) or g.get('dist', 999) <= 60
            if ok:
                r = _summary(lang, g['title'])
                if r:
                    return r
    return None


def resolve_image(info, lat=None, lon=None, names=()):
    """يبحث عن صورة صحيحة للمكان بالتدرّج، ويرجع dict فيه src/page/site/general أو None.
    الترتيب: صورة المكان نفسه (وسوم OSM، ويكيداتا، بحث جغرافي بالاسم) ثم صورة عامة موسومة.
    يرمي استثناء فقط إذا فشلت كل المحاولات بسبب الشبكة (فلا يُخزَّن الفشل)."""
    own, errors, tried = info.get('own') or {}, 0, 0

    def attempt(fn, *a):
        nonlocal errors, tried
        tried += 1
        try:
            return fn(*a)
        except Exception:
            errors += 1
            return None

    res = None
    if own.get('commons'):
        res = _commons_file(own['commons']) if own['commons'].lower().startswith('file:') else None
    if not res and own.get('wikipedia') and ':' in own['wikipedia']:
        lang, title = own['wikipedia'].split(':', 1)
        res = attempt(_summary, lang.strip(), title.strip())
    if not res and own.get('wikidata'):
        res = attempt(_from_wikidata, own['wikidata'])
    for lang, title in info.get('cands', []):          # الحرمان: عناوين محددة
        if res:
            break
        res = attempt(_summary, lang, title)
    if not res and lat is not None and not info.get('cands'):
        res = attempt(_geo_match, lat, lon, [n for n in names if n])
    if res:
        return {**res, 'general': False}
    for lang, title in info.get('fallback', []):         # صورة عامة موسومة
        res = attempt(_summary, lang, title)
        if res:
            return {**res, 'general': True}
    if tried and errors == tried:
        raise RuntimeError('network')
    return None