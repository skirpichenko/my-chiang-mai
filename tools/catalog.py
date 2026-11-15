"""Catalog pipeline for the Telegram channel «Мой Чиангмай». Paths are relative to the repo root.

  python3 tools/catalog.py status                    what the catalog reflects, what is pending
  python3 tools/catalog.py diff                      changed/new posts of work/result.json -> work/inc/<tag>/p*.txt
  python3 tools/catalog.py pending                   JSON {"root", "pairs": [[part.txt, part.jsonl], ...]} still to extract
  python3 tools/catalog.py build [--contacts] [--force]   merge all extracted entries -> docs/catalog.json
                                                     (with each item's city region, see tools/geo.py)
  python3 tools/catalog.py split                     full re-split into work/chunks (full rebuild only)

Contacts (phones, handles, emails) are left out of catalog.json unless --contacts is given.
"""
import collections, glob, hashlib, json, os, re, shutil, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, 'work')
EXPORT = os.path.join(WORK, 'result.json')
STATE = os.path.join(WORK, 'state.json')
EXPORTS = os.path.join(WORK, 'exports')
CHUNKS = os.path.join(WORK, 'chunks')
OUT = os.path.join(WORK, 'out')
INC = os.path.join(WORK, 'inc')
CATALOG = os.path.join(ROOT, 'docs', 'catalog.json')
PART_CHARS, PARTS_PER_CHUNK = 41000, 4

CATEGORIES = ['food_cafe', 'food_restaurant', 'food_bar', 'food_bakery', 'food_products',
              'shopping_market', 'shopping_store', 'kids', 'health', 'beauty_relax',
              'sport_practice', 'services', 'housing', 'work_study', 'leisure',
              'music_venues', 'events', 'travel', 'info', 'community']
KINDS = {'place', 'service', 'event', 'info'}
MAPS_RE = re.compile(r'https?://(?:maps\.app\.goo\.gl|goo\.gl/maps|(?:www\.)?google\.[a-z.]+/maps|maps\.google\.[a-z.]+)[^\s<>)\]]*')


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))


# ---------- posts and part files ----------

def render(m):
    t = m.get('text', '')
    if isinstance(t, str):
        return t
    out = []
    for x in t:
        if isinstance(x, str):
            out.append(x)
        elif x.get('type') == 'text_link':
            out.append(f"{x.get('text', '')} <{x.get('href', '')}>")
        else:
            out.append(x.get('text', ''))
    return ''.join(out)


def load_posts(path=EXPORT):
    """Post id -> header line and text in part-file format, for every message (text may be empty)."""
    posts = collections.OrderedDict()
    for m in load_json(path)['messages']:
        if m.get('type') != 'message':
            continue
        head = f"=== #{m['id']} | {m['date'][:10]}"
        if m.get('reply_to_message_id'):
            head += f" | reply_to=#{m['reply_to_message_id']}"
        if m.get('forwarded_from'):
            head += f" | fwd={m['forwarded_from']}"
        posts[m['id']] = {'head': head, 'text': render(m).strip(), 'reply_to': m.get('reply_to_message_id')}
    return posts


def digest(p):
    return hashlib.sha1((p['head'] + '\n' + p['text']).encode('utf-8')).hexdigest()[:16]


def state_of(posts):
    return {str(i): digest(p) for i, p in posts.items()}


def write_parts(posts, dest, name):
    blocks = [p['head'] + '\n' + p['text'] + '\n' for p in posts if p['text']]
    parts, cur, n = [], [], 0
    for b in blocks:
        if cur and n + len(b) > PART_CHARS:
            parts.append(cur)
            cur, n = [], 0
        cur.append(b)
        n += len(b)
    if cur:
        parts.append(cur)
    for i, part in enumerate(parts):
        with open(os.path.join(dest, name(i)), 'w', encoding='utf-8') as f:
            f.write('\n'.join(part))
    return len(blocks), len(parts)


def inc_dirs():
    return sorted(d for d in glob.glob(os.path.join(INC, '*')) if os.path.isdir(d))


def part_pairs():
    pairs = [(f, os.path.join(OUT, os.path.basename(f)[:-4] + '.jsonl'))
             for f in sorted(glob.glob(os.path.join(CHUNKS, '*.txt')))]
    for d in inc_dirs():
        pairs += [(f, f[:-4] + '.jsonl') for f in sorted(glob.glob(os.path.join(d, 'p*.txt')))]
    return pairs


def valid_jsonl(path):
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    json.loads(line)
        return True
    except (OSError, ValueError):
        return False


def pending():
    return [[i, o] for i, o in part_pairs() if not valid_jsonl(o)]


# ---------- commands ----------

def cmd_split():
    if glob.glob(os.path.join(OUT, '*.jsonl')) or inc_dirs():
        sys.exit('work/out or work/inc is not empty. They hold the paid-for extraction: move them aside first.')
    os.makedirs(CHUNKS, exist_ok=True)
    for f in glob.glob(os.path.join(CHUNKS, '*.txt')):
        os.remove(f)
    posts = load_posts()
    n, k = write_parts(posts.values(), CHUNKS, lambda i: f'c{i // PARTS_PER_CHUNK:02d}_p{i % PARTS_PER_CHUNK}.txt')
    save_json(STATE, state_of(posts))
    print(n, 'posts with text ->', k, 'part files in work/chunks; work/state.json reset')


def cmd_diff():
    if not os.path.exists(STATE):
        sys.exit('work/state.json is missing: nothing to compare with (a full build starts with `split`).')
    old = load_json(STATE)
    posts = load_posts()
    new = state_of(posts)
    changed = sorted(int(i) for i in new if old.get(i) != new[i])
    deleted = sorted(int(i) for i in old if i not in new)
    if not changed and not deleted:
        print('no changes since the last update')
        return
    # Re-extract the reply parent and direct replies of each changed post too, so threads stay together.
    ids, cs = set(changed), set(changed)
    for i in changed:
        if posts[i]['reply_to'] in posts:
            ids.add(posts[i]['reply_to'])
    ids |= {i for i, p in posts.items() if p['reply_to'] in cs}
    tag = time.strftime('%Y%m%d-%H%M%S')
    d = os.path.join(INC, tag)
    os.makedirs(d)
    os.makedirs(EXPORTS, exist_ok=True)
    n, k = write_parts([p for i, p in posts.items() if i in ids], d, lambda i: f'p{i}.txt')
    save_json(os.path.join(d, 'posts.json'), {'tag': tag, 'changed': changed, 'deleted': deleted,
                                              'posts': sorted(ids | set(deleted))})
    shutil.copy2(STATE, os.path.join(d, 'state_before.json'))
    shutil.copy2(EXPORT, os.path.join(EXPORTS, tag + '.json'))
    save_json(STATE, new)
    print(f'update {tag}: {len(changed)} changed or new posts, {len(deleted)} deleted; '
          f'{n} posts with text (incl. thread context) -> {k} part files in work/inc/{tag}/')
    print('changed ids:', changed[:60], '...' if len(changed) > 60 else '')


def cmd_pending():
    print(json.dumps({'root': ROOT, 'pairs': pending()}, ensure_ascii=False))


def cmd_status():
    if os.path.exists(STATE):
        state = load_json(STATE)
        print('work/state.json:', len(state), 'posts')
        if os.path.exists(EXPORT):
            new = state_of(load_posts())
            n = sum(1 for i in new if state.get(i) != new[i]) + sum(1 for i in state if i not in new)
            print('work/result.json:', f'{n} posts differ from state.json -> run diff' if n else 'nothing new')
    for d in inc_dirs():
        meta = load_json(os.path.join(d, 'posts.json'))
        print(f"update {meta['tag']}: {len(meta['changed'])} changed/new, {len(meta['deleted'])} deleted")
    todo = pending()
    print(len(todo), 'part files pending extraction')
    for i, _ in todo:
        print('  ', os.path.relpath(i, ROOT))
    if os.path.exists(CATALOG):
        c = load_json(CATALOG)
        print('catalog.json:', len(c['items']), 'items, posts until', c['built_from_posts_until'])


def norm_name(s):
    return re.sub(r'[^0-9a-zа-яё฀-๿一-鿿]+', ' ', (s or '').lower().replace('ё', 'е')).strip()


def maps_key(url):
    # Only short links carry a disposable tracking query; long links keep the place in the query.
    u = re.sub(r'^https?://', '', url.strip())
    if u.startswith(('maps.app.goo.gl/', 'goo.gl/maps/')):
        u = u.split('?')[0]
    return u.rstrip('/')


def compact(s):
    return norm_name(s).replace(' ', '')


def http(url):
    return isinstance(url, str) and re.match(r'https?://', url)


TRACKING = re.compile(r'(utm_\w+|fbclid|gclid|igsh|igshid|mibextid)$', re.I)


def clean_url(url):
    """The link without tracking parameters (utm_*, fbclid, igsh, mibextid; g_st on short Maps links)."""
    if not http(url) or '?' not in url:
        return url
    base, _, rest = url.partition('?')
    query, hash_, frag = rest.partition('#')
    short_maps = re.match(r'https?://(maps\.app\.goo\.gl|goo\.gl/maps)/', base)
    kept = [p for p in query.split('&') if p
            and not TRACKING.match(p.split('=', 1)[0]) and not (short_maps and p.split('=', 1)[0] == 'g_st')]
    return base + ('?' + '&'.join(kept) if kept else '') + hash_ + frag


def cmd_build(with_contacts, force):
    todo = pending()
    if todo and not force:
        sys.exit(f'{len(todo)} part files still need extraction (see `status`). '
                 '--force builds anyway, and the posts in them drop out of the catalog.')
    msgs = load_json(EXPORT)['messages']
    post_date = {m['id']: m['date'][:10] for m in msgs}

    # Each post belongs to its newest extraction: an update supersedes older entries of the posts it re-extracted.
    owner = {}
    for d in inc_dirs():
        for i in load_json(os.path.join(d, 'posts.json'))['posts']:
            owner[i] = os.path.basename(d)
    files = [(None, f) for f in sorted(glob.glob(os.path.join(OUT, '*.jsonl')))]
    for d in inc_dirs():
        files += [(os.path.basename(d), f) for f in sorted(glob.glob(os.path.join(d, 'p*.jsonl')))]

    raw, bad = [], collections.Counter()
    for tag, f in files:
        with open(f, encoding='utf-8') as fh:
            lines = fh.readlines()
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                bad['invalid json'] += 1
                continue
            if not isinstance(e, dict) or e.get('kind') not in KINDS or e.get('category') not in CATEGORIES or not e.get('name'):
                bad['bad kind/category/name'] += 1
                continue
            ids = [i for i in (e.get('post_ids') or []) if isinstance(i, int) and i in post_date]
            e['post_ids'] = [i for i in ids if owner.get(i) == tag]
            if not e['post_ids']:
                bad['superseded by a later update' if ids else 'no valid post id'] += 1
                continue
            e['maps_url'] = clean_url(e.get('maps_url')) if http(e.get('maps_url')) else None
            e['links'] = [clean_url(u) for u in e.get('links') or []]
            raw.append(e)

    groups = collections.OrderedDict()
    clusters = collections.defaultdict(list)
    for e in raw:
        if e['kind'] == 'event':
            key = ('e', norm_name(e['name']), e.get('event_date'))
        elif e['maps_url']:
            # Posts sometimes reuse one link for different places, so a link groups only similar names.
            mk, c = maps_key(e['maps_url']), compact(e['name'])
            rep = next((r for r in clusters[mk] if c in r or r in c), None)
            if rep is None:
                rep = c
                clusters[mk].append(c)
            key = ('m', mk, rep)
        else:
            key = ('n', e['kind'], norm_name(e['name']), e.get('city'))
        groups.setdefault(key, []).append(e)

    # A place mentioned without a map link joins the single map-linked place of the same name and city.
    by_name = collections.defaultdict(set)
    for key, es in groups.items():
        if key[0] == 'm':
            for e in es:
                by_name[(norm_name(e['name']), e.get('city'))].add(key)
    for key in [k for k in groups if k[0] == 'n']:
        targets = by_name.get((key[2], key[3]))
        if targets and len(targets) == 1:
            groups[next(iter(targets))].extend(groups.pop(key))

    def union(es, field):
        seen, out = set(), []
        for e in es:
            for v in e.get(field) or []:
                if isinstance(v, str) and v.strip() and v not in seen:
                    seen.add(v)
                    out.append(v.strip())
        return out

    def first(es, field):
        return next((e[field] for e in es if e.get(field)), None)

    catalog = []
    for es in groups.values():
        es.sort(key=lambda e: max(post_date[i] for i in e['post_ids']), reverse=True)
        ids = sorted({i for e in es for i in e['post_ids']}, reverse=True)
        item = {
            'k': es[0]['kind'],
            'n': es[0]['name'].strip(),
            'c': collections.Counter(e['category'] for e in es).most_common(1)[0][0],
            's': first(es, 'subcategory'),
            'd': max((e.get('summary') or '' for e in es), key=len),
            'city': first(es, 'city') or 'Чиангмай',
            'a': first(es, 'area'),
            'm': first(es, 'maps_url'),
            'l': [u for u in union(es, 'links') if http(u)][:6],
            'p': first(es, 'price'),
            'h': first(es, 'hours'),
            't': [t.lower() for t in union(es, 'tags')][:8],
            'ids': ids[:12],
            'last': max(post_date[i] for i in ids),
            'ed': first(es, 'event_date'),
            'r': bool(first(es, 'recurring')),
        }
        if with_contacts:
            item['ct'] = union(es, 'contacts')[:6]
        catalog.append({k: v for k, v in item.items() if v not in (None, [], '', False)})

    catalog.sort(key=lambda x: x['last'], reverse=True)
    for i, item in enumerate(catalog):
        item['id'] = i

    old = load_json(CATALOG)['items'] if os.path.exists(CATALOG) else []
    # City regions (tools/geo.py): each item's `z`, from its map link's address, the district borders or its area text.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import geo
    geo.report(catalog)
    save_json(CATALOG, {'built_from_posts_until': max(post_date.values()), 'items': catalog})

    names = lambda items: {(x['k'], x['n']) for x in items}
    added, gone = names(catalog) - names(old), names(old) - names(catalog)
    print('raw entries', len(raw), '| skipped', dict(bad))
    print('catalog items', len(old), '->', len(catalog), dict(collections.Counter(i['k'] for i in catalog)))
    print(f'names added {len(added)}:', sorted(n for _, n in added)[:30])
    print(f'names gone {len(gone)}:', sorted(n for _, n in gone)[:30])

    # Coverage: every map link in the posts should be some entry's maps_url.
    src_links = {}
    for m in msgs:
        for u in MAPS_RE.findall(render(m)):
            src_links.setdefault(maps_key(u), m['id'])
    have = {maps_key(e['maps_url']) for e in raw if e['maps_url']}
    missing = {k: v for k, v in src_links.items() if k not in have}
    print('map links in posts', len(src_links), '| used as maps_url', len(src_links) - len(missing), '| not used', len(missing))
    print('posts with unused map links (first 40)', sorted(set(missing.values()))[:40])
    print('catalog.json bytes', os.path.getsize(CATALOG))


if __name__ == '__main__':
    args = sys.argv[1:]
    cmd = args[0] if args else 'status'
    if cmd == 'build':
        cmd_build('--contacts' in args, '--force' in args)
    elif cmd in ('status', 'diff', 'pending', 'split'):
        globals()['cmd_' + cmd]()
    else:
        sys.exit(__doc__)
