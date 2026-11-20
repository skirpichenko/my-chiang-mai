"""City regions for the catalog: which part of Chiang Mai each place is in. Paths are relative to the repo root.

  python3 -I tools/geo.py resolve [--limit N]   open each short map link once and keep Google's redirect (network)
  python3 -I tools/geo.py borders [--from FILE] the province's district borders from OpenStreetMap (network, once);
                                                --from reads a saved Overpass answer (see BORDERS_QUERY)
  python3 -I tools/geo.py stats [--samples N]   regions of the current docs/catalog.json items; writes nothing

A short link (maps.app.goo.gl) redirects to a Google Maps address. Only that redirect is read, never the Maps page.
The redirect holds one or more of: the place's coordinates, a Plus Code, and its address. The address usually names
the subdistrict (tambon) or district (amphoe), and tools/regions.json groups those into the regions the site shows.
Coordinates without a usable address get their district from the OpenStreetMap borders (tools/regions/districts.json);
inside the city they take the region of the nearest places whose region is known. Items with no usable link fall
back to their area text. `catalog.py build` calls assign() to add each item's region as `z`.

work/geo.json caches every redirect, so each link is opened once. A redirect to a block or captcha page stops the run:
it never retries around one.
"""
import collections, http.client, json, math, os, re, sys, time, urllib.error, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, 'work')
CACHE = os.path.join(WORK, 'geo.json')
REGIONS = os.path.join(ROOT, 'tools', 'regions.json')
DISTRICTS = os.path.join(ROOT, 'tools', 'regions', 'districts.json')
CATALOG = os.path.join(ROOT, 'docs', 'catalog.json')

SHORT_HOSTS = ('maps.app.goo.gl', 'goo.gl', 'g.page', 'share.google')
PAUSE = 1.0          # seconds between requests
UA = 'Mozilla/5.0 (compatible; my-chiang-mai-catalog/1.0)'


def load_json(path, default=None):
    if default is not None and not os.path.exists(path):
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=0)
    os.replace(tmp, path)


def host(u):
    return (urllib.parse.urlsplit(u).hostname or '').lower()


def is_short(u):
    return host(u) in SHORT_HOSTS


# ---------- resolve ----------

class Blocked(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def hop(u):
    """(status, Location) for one request, without following the redirect."""
    req = urllib.request.Request(u, headers={'User-Agent': UA})
    try:
        with OPENER.open(req, timeout=20) as r:
            return r.status, r.headers.get('Location')
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get('Location')


def follow(u):
    """The first redirect target outside the short-link hosts, or None. Raises Blocked on a block or captcha."""
    for _ in range(4):
        status, loc = hop(u)
        if status in (403, 429, 503) or (loc and ('/sorry/' in loc or 'consent.google' in loc)):
            raise Blocked(f'{status} {loc or ""}'[:200])
        if status not in (301, 302, 303, 307, 308) or not loc:
            return None
        loc = urllib.parse.urljoin(u, loc)
        if not is_short(loc):
            return loc
        u = loc
    return None


def catalog_links():
    """Every map link the catalog can use: the items' links, plus all map links in the posts."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import catalog as cat
    links = {it['m'] for it in load_json(CATALOG, {'items': []})['items'] if it.get('m')}
    if os.path.exists(cat.EXPORT):
        for m in load_json(cat.EXPORT)['messages']:
            if m.get('type') == 'message':
                links |= {cat.clean_url(u) for u in cat.MAPS_RE.findall(cat.render(m))}
    return links


def cmd_resolve(limit):
    cache = load_json(CACHE, {'links': {}})
    todo = sorted(u for u in catalog_links() if is_short(u) and u not in cache['links'])
    if limit:
        todo = todo[:limit]
    print(f'{len(cache["links"])} links cached; resolving {len(todo)} now, about {len(todo) * PAUSE / 60:.0f} min',
          flush=True)
    start, got = time.time(), 0
    for n, u in enumerate(todo, 1):
        try:
            loc = follow(u)
        except Blocked as e:
            save_json(CACHE, cache)
            sys.exit(f'stopped: Google answered with a block or captcha ({e}). Nothing was retried; '
                     f'{n - 1} links resolved this run. Try again much later.')
        except (ValueError, http.client.InvalidURL):
            loc = None   # a malformed link (a space or a control character in it): nothing to open
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f'  network error on {u}: {e}; left for the next run', flush=True)
            time.sleep(PAUSE * 5)
            continue
        cache['links'][u] = {'to': loc, 'at': time.strftime('%Y-%m-%d')}
        got += bool(loc)
        if n % 50 == 0 or n == len(todo):
            save_json(CACHE, cache)
            print(f'  {n}/{len(todo)} done, {got} redirects, {time.time() - start:.0f}s', flush=True)
        time.sleep(PAUSE)
    save_json(CACHE, cache)
    print(f'done: {len(cache["links"])} links cached', flush=True)


# ---------- district borders (OpenStreetMap) ----------

OVERPASS = 'https://overpass-api.de/api/interpreter'
BORDERS_QUERY = ('[out:json][timeout:180];area["ISO3166-2"="TH-50"]->.p;'
                 'relation(area.p)["boundary"="administrative"]["admin_level"="6"];out geom;')
SIMPLIFY = 0.0003    # degrees, about 30 m


def join_rings(ways):
    """Join the ways of a boundary into closed rings."""
    segs, out = [w for w in ways if len(w) >= 2], []
    while segs:
        ring = segs.pop(0)
        while ring[0] != ring[-1]:
            for i, s in enumerate(segs):
                if s[0] == ring[-1]:
                    ring = ring + s[1:]
                elif s[-1] == ring[-1]:
                    ring = ring + s[::-1][1:]
                elif s[-1] == ring[0]:
                    ring = s[:-1] + ring
                elif s[0] == ring[0]:
                    ring = s[::-1][:-1] + ring
                else:
                    continue
                segs.pop(i)
                break
            else:
                break   # a gap in the data: keep what joins
        if len(ring) >= 4:
            out.append(ring)
    return out


def simplify(pts, tol):
    """Douglas-Peucker."""
    if len(pts) < 5:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ay, ax), (by, bx) = pts[a], pts[b]
        dx, dy, best, bi = bx - ax, by - ay, 0.0, None
        ll = dx * dx + dy * dy
        for i in range(a + 1, b):
            py, px = pts[i]
            t = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
            d = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d > best:
                best, bi = d, i
        if bi is not None and best > tol * tol:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def cmd_borders(path=None):
    if path:   # older Pythons on macOS can fail the TLS handshake with Overpass; curl can fetch the answer instead
        data = load_json(path)
    else:
        req = urllib.request.Request(OVERPASS, data=urllib.parse.urlencode({'data': BORDERS_QUERY}).encode(),
                                     headers={'User-Agent': UA, 'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=240) as r:
            data = json.load(r)
    out = {}
    for rel in data['elements']:
        name = (rel['tags'].get('name:en') or '').replace(' District', '').strip()
        if not name:
            continue
        parts = {'outer': [], 'inner': []}
        for m in rel.get('members', []):
            if m['type'] == 'way' and m.get('geometry'):
                parts['inner' if m.get('role') == 'inner' else 'outer'].append(
                    [(round(g['lat'], 7), round(g['lon'], 7)) for g in m['geometry']])
        rings = {k: [[[round(y, 5), round(x, 5)] for y, x in simplify(r, SIMPLIFY)] for r in join_rings(v)]
                 for k, v in parts.items()}
        out[name] = {'th': rel['tags'].get('name', ''), **rings}
    os.makedirs(os.path.dirname(DISTRICTS), exist_ok=True)
    with open(DISTRICTS, 'w', encoding='utf-8') as f:
        json.dump({'source': '© OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright)',
                   'districts': out}, f, ensure_ascii=False, separators=(',', ':'))
    print(f'{len(out)} districts, {sum(len(r) for d in out.values() for r in d["outer"])} points '
          f'-> {os.path.relpath(DISTRICTS, ROOT)} ({os.path.getsize(DISTRICTS)} bytes)')


def load_districts():
    if not os.path.exists(DISTRICTS):
        return {}
    ds = load_json(DISTRICTS)['districts']
    for d in ds.values():
        ys = [p[0] for r in d['outer'] for p in r]
        xs = [p[1] for r in d['outer'] for p in r]
        d['box'] = (min(ys), max(ys), min(xs), max(xs))
        d['center'] = ((min(ys) + max(ys)) / 2, (min(xs) + max(xs)) / 2)
    return ds


def in_ring(lat, lng, ring):
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def district_at(lat, lng, ds):
    for name, d in ds.items():
        y0, y1, x0, x1 = d['box']
        if y0 <= lat <= y1 and x0 <= lng <= x1 and any(in_ring(lat, lng, r) for r in d['outer']) \
                and not any(in_ring(lat, lng, r) for r in d['inner']):
            return name
    return None


# ---------- Plus Codes ----------

PLUS_ALPHABET = '23456789CFGHJMPQRVWX'
PLUS_RE = re.compile(r'(?<![0-9A-Za-z])([23456789CFGHJMPQRVWX]{4,8})\+([23456789CFGHJMPQRVWX]{0,3})(?![0-9A-Za-z])')
CITY_CENTER = (18.7883, 98.9853)
PROVINCE_CITIES = ('Чиангмай', 'Чиангдао', 'Кальяниваттана')   # catalog `city` values inside Chiang Mai province


def plus_decode(code):
    """Centre of a full (8+ digit) Plus Code."""
    c, A = code.replace('+', ''), PLUS_ALPHABET
    lat, lng, step = -90.0, -180.0, 20.0
    for i in range(0, min(len(c), 10), 2):
        lat += A.index(c[i]) * step
        lng += A.index(c[i + 1]) * step
        if i < 8:
            step /= 20
    la = lo = step
    for ch in c[10:]:
        la, lo = la / 5, lo / 4
        k = A.index(ch)
        lat += (k // 4) * la
        lng += (k % 4) * lo
    return lat + la / 2, lng + lo / 2


def plus_prefix(lat, lng, digits):
    lat, lng, out, step = lat + 90, lng + 180, '', 20.0
    for _ in range(digits // 2):
        out += PLUS_ALPHABET[int(lat // step)] + PLUS_ALPHABET[int(lng // step)]
        lat, lng, step = lat % step, lng % step, step / 20
    return out


def plus_recover(head, tail, ref):
    """Coordinates of a Plus Code; a short one is completed with the reference point nearest to it."""
    if len(head) == 8:
        return plus_decode(head + '+' + tail)
    missing = 8 - len(head)
    cell = 20.0 / 20 ** (missing // 2 - 1)   # size of the dropped part's cell, in degrees
    best = None
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            y, x = plus_decode(plus_prefix(ref[0] + dy * cell, ref[1] + dx * cell, missing) + head + '+' + tail)
            d = (y - ref[0]) ** 2 + (x - ref[1]) ** 2
            if best is None or d < best[0]:
                best = (d, y, x)
    return best[1], best[2]


# ---------- reading a Google Maps address ----------

PIN_RE = re.compile(r'!3d(-?\d{1,2}\.\d+)!4d(-?\d{1,3}\.\d+)')
AT_RE = re.compile(r'/@(-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)')
LATLNG_RE = re.compile(r'^\s*(-?\d{1,2}\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})\s*$')
POSTCODE_RE = re.compile(r'(?<!\d)(\d{5})(?!\d)')
# In a raw query a Plus Code's '+' looks like an encoded space ('RX2J+239+Sangwiroon'), so look before decoding.
RAW_PLUS_RE = re.compile(r'(?:[?&](?:q|query)=|/maps/place/)([23456789CFGHJMPQRVWX]{4,8})(?:\+|%2B)'
                         r'([23456789CFGHJMPQRVWX]{2,3})(?=\+|%20|%2C|,|&|/|$)')


def parse_maps(url):
    """{'coords', 'text', 'plus', 'search'} from a Google Maps link."""
    p = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qs(p.query)
    path = urllib.parse.unquote(p.path)
    text = (q.get('q') or q.get('query') or [''])[0]
    if '/maps/place/' in path:
        seg = path.split('/maps/place/', 1)[1].split('/')[0].replace('+', ' ')
        text = text or seg
    coords = None
    m = PIN_RE.search(urllib.parse.unquote(url))
    if m:
        coords = (float(m[1]), float(m[2]))
    elif LATLNG_RE.match(text):
        m = LATLNG_RE.match(text)
        coords, text = (float(m[1]), float(m[2])), ''
    elif '/maps/place/' in path and AT_RE.search(path):
        m = AT_RE.search(path)
        coords = (float(m[1]), float(m[2]))
    plus = RAW_PLUS_RE.search(url) or PLUS_RE.search(text)
    return {'coords': coords, 'text': text, 'plus': (plus[1], plus[2]) if plus else None,
            'search': '/maps/search' in path or 'query' in q}


PLACE_RE = re.compile(r'(?:ftid=|!1s)(0x[0-9a-f]+:0x[0-9a-f]+)', re.I)


def place_ids():
    """A function: map link -> the Google place it opens (its feature id), read from the link itself or from its
    redirect in work/geo.json; None when the link names no place (a search, bare coordinates) or is not resolved yet.
    `catalog.py build` uses it so that two different links to one place count as one link."""
    cache = load_json(CACHE)['links'] if os.path.exists(CACHE) else {}

    def place_of(url):
        loc = (cache.get(url) or {}).get('to') if is_short(url) else url
        m = PLACE_RE.search(urllib.parse.unquote(loc or ''))
        return 'place:' + m[1].lower() if m else None
    return place_of


def norm(s):
    return ' ' + re.sub(r'[\s,;/()]+', ' ', (s or '').lower().replace('ё', 'е')) + ' '


class Regions:
    def __init__(self):
        cfg = load_json(REGIONS)
        self.order = [r['id'] for r in cfg['regions']]
        self.names = {r['id']: {'ru': r['ru'], 'en': r['en']} for r in cfg['regions']}
        self.city = [r['id'] for r in cfg['regions'] if r.get('subdistricts')]
        self.of_sub = {s: r['id'] for r in cfg['regions'] for s in r.get('subdistricts', [])}
        self.of_district = {d: r['id'] for r in cfg['regions'] for d in r.get('districts', [])}
        self.of_district['Mueang Chiang Mai'] = None
        self.postcodes = cfg['postcodes']
        self.spell = {name: [self.pattern(v) for v in vs] for name, vs in cfg['spellings'].items()}
        self.area = [(r['id'], [self.pattern(a) for a in r.get('area', [])]) for r in cfg['regions']]

    @staticmethod
    def pattern(v):
        v = v.lower()
        if re.search(r'[a-zа-я]', v):   # Latin or Cyrillic: whole words only
            return re.compile(r'(?<![a-zа-я0-9])' + re.escape(v) + r'(?![a-zа-я0-9])')
        return re.compile(re.escape(v))   # Thai has no spaces between words

    def find(self, s, name, strong=False):
        """Last position of a place name in s; strong=True asks for 'X District' / 'Amphoe X' / 'อ.X'."""
        best = -1
        for p in self.spell.get(name, []):
            for m in p.finditer(s):
                if strong:
                    before, after = s[max(0, m.start() - 8):m.start()], s[m.end():m.end() + 10]
                    thai = not re.search(r'[a-z]', m[0])
                    if not (after.startswith(' district') or before.endswith('amphoe ') or
                            (thai and re.search(r'(อ\.|อำเภอ)\s*$', before))):
                        continue
                best = max(best, m.start())
        return best

    def from_address(self, text):
        """(district, region): the district named or implied by the address, and the region if that settles it."""
        s = norm(text)
        posts = POSTCODE_RE.findall(s)
        post = posts[-1] if posts else None
        if post and not post.startswith('50') and post != '58130':
            return 'outside', None
        named = [(self.find(s, d, strong=True), d) for d in self.of_district]
        named = [x for x in named if x[0] >= 0]
        district = max(named)[1] if named else self.postcodes.get(post)
        if district and district != 'Mueang Chiang Mai':
            return district, self.of_district.get(district)
        subs = [(self.find(s, sub), sub) for sub in self.of_sub]
        subs = [x for x in subs if x[0] >= 0]
        if subs:
            return 'Mueang Chiang Mai', self.of_sub[max(subs)[1]]
        return district, None

    def from_area(self, text, city_only=False):
        """Region named in a free text (area field, search query); city_only: the city's own regions only."""
        s = norm(text)
        hits = [(m.start(), rid) for rid, ps in self.area for p in ps for m in [p.search(s)] if m
                and (not city_only or rid in self.city)]
        return min(hits)[1] if hits else None


def km(a, b):
    dy = (a[0] - b[0]) * 111.2
    dx = (a[1] - b[1]) * 111.2 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def assign(items, quiet=False):
    """Set item['z'] (region id) where it can be told. Returns a report of how each item was placed."""
    if not os.path.exists(CACHE):
        if not quiet:
            print('regions: work/geo.json is missing; run `python3 -I tools/geo.py resolve` first')
        return None
    R, cache, ds = Regions(), load_json(CACHE)['links'], load_districts()
    how, info = collections.Counter(), {}
    for it in items:
        it.pop('z', None)
        u = it.get('m')
        if not u or it.get('city', 'Чиангмай') not in PROVINCE_CITIES:
            continue
        loc = cache.get(u, {}).get('to') if is_short(u) else u
        if is_short(u) and u not in cache:
            how['link not resolved yet'] += 1
            continue
        if not loc:
            continue
        p = parse_maps(loc)
        district, region = R.from_address(p['text']) if not p['search'] else (None, None)
        if district == 'Mueang Chiang Mai' and not region:
            # A city address without a subdistrict often names a street or landmark: "Nimmanahaeminda Rd", "Tha Phae Rd".
            region = R.from_area(p['text'], city_only=True)
        if p['search'] and it.get('city') == 'Чиангмай':
            region = R.from_area(p['text'])
        coords = p['coords']
        if not coords and p['plus']:
            ref = ds[district]['center'] if district in ds else CITY_CENTER
            coords = plus_recover(*p['plus'], ref)
        info[id(it)] = (district, region, coords)
    # Coordinates without a region: the district from the borders; inside the city, the nearest known places.
    known = [(c, r) for d, r, c in info.values() if c and r in R.city]
    for it in items:
        if id(it) not in info:
            continue
        district, region, coords = info[id(it)]
        if region:
            it['z'], it['_how'] = region, 'address'
            how['from the address'] += 1
            continue
        if district == 'outside':
            how['outside the province'] += 1
            continue
        if coords and ds and district is None:
            district = district_at(*coords, ds) or 'outside'
            if district == 'outside':
                how['outside the province'] += 1
                continue
            if district != 'Mueang Chiang Mai':
                it['z'], it['_how'] = R.of_district.get(district), 'borders'
                how['from the coordinates'] += 1
                continue
        if coords and district == 'Mueang Chiang Mai':
            near = sorted((km(coords, c), r) for c, r in known)[:5]
            near = [r for d, r in near if d <= 1.5]
            if near:
                it['z'], it['_how'] = collections.Counter(near).most_common(1)[0][0], 'nearby'
                how['from nearby places'] += 1
                continue
    for it in items:
        if 'z' not in it and it.get('city') == 'Чиангмай' and it.get('a'):
            z = R.from_area(it['a'])
            if z:
                it['z'], it['_how'] = z, 'area'
                how['from the area text'] += 1
    return how


def report(items, samples=0):
    how = assign(items)
    if how is None:
        return
    R = Regions()
    cm = [it for it in items if it.get('city') == 'Чиангмай']
    per = collections.Counter(it.get('z') for it in cm)
    print('regions (Chiang Mai items):', len(cm), '| with a region', len(cm) - per[None], '| without', per[None])
    print('  how placed (all items):', dict(how))
    for rid in R.order:
        line = f'  {per[rid]:>5}  {R.names[rid]["ru"]}'
        if samples:
            names = [f"{it['n'][:40]} [{it['_how']}{': ' + it['a'][:30] if it['_how'] == 'area' else ''}]"
                     for it in cm if it.get('z') == rid][:samples]
            line += '\n           ' + '\n           '.join(names)
        print(line)
    odd = [it for it in items if it.get('z') and it.get('city') not in ('Чиангмай', 'Чиангдао', 'Кальяниваттана')]
    if odd:
        print('  items of other cities with a Chiang Mai region:', [(it['n'], it['city'], it['z']) for it in odd[:15]])
    no = collections.Counter('map link' if it.get('m') else ('area text only' if it.get('a') else 'no place info')
                             for it in cm if not it.get('z') and it.get('k') in ('place', 'service', 'event'))
    print('  Chiang Mai places, services and events without a region:', dict(no))
    for it in items:
        it.pop('_how', None)


def cmd_stats(samples):
    items = load_json(CATALOG)['items']
    report(items, samples)


if __name__ == '__main__':
    args = sys.argv[1:]
    cmd = args[0] if args else ''

    def opt(name, default=None):
        return int(args[args.index(name) + 1]) if name in args else default

    if cmd == 'resolve':
        cmd_resolve(opt('--limit'))
    elif cmd == 'borders':
        cmd_borders(args[args.index('--from') + 1] if '--from' in args else None)
    elif cmd == 'stats':
        cmd_stats(opt('--samples', 6))
    else:
        sys.exit(__doc__)
