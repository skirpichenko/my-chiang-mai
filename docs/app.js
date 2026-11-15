// The catalog site, shared by the Russian page (index.html) and the English one (en/index.html).
// Each page sets window.SITE = {lang, data, other} before loading this file:
//   lang   'ru' or 'en' (picks the strings below)
//   data   URL of the catalog JSON (catalog.json or catalog.en.json)
//   other  URL of the page in the other language
const SITE = window.SITE || { lang: 'ru', data: 'catalog.json', other: 'en/' };
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const STRINGS = {
  ru: {
    channel: 'my_chiangmai',   // username of the public channel the posts are in, without "@"
    home: 'Чиангмай',
    cats: {
      food_cafe: 'Кафе и кофейни', food_restaurant: 'Рестораны', food_bar: 'Бары',
      food_bakery: 'Пекарни и десерты', food_products: 'Продукты', shopping_market: 'Рынки',
      shopping_store: 'Магазины', kids: 'Детям', health: 'Здоровье', beauty_relax: 'Массаж и спа',
      sport_practice: 'Спорт и йога', services: 'Услуги', housing: 'Жильё и отели',
      work_study: 'Работа и учёба', leisure: 'Досуг и природа', music_venues: 'Живая музыка',
      events: 'Афиша', travel: 'Поездки', info: 'Полезное', community: 'Сообщества',
    },
    // City regions, in the order of tools/regions.json; items carry the id as `z`.
    areas: { 'old-city': 'Старый город', 'nimman': 'Нимман и Сутхеп', 'santitham': 'Сантитам и Чанг Пхыак', 'riverside': 'Тха Пае и река', 'south': 'Юг города', 'mae-hia': 'Мае Хиа', 'northeast': 'Северо-восток города', 'hang-dong': 'Ханг Донг', 'mae-rim': 'Мае Рим', 'san-sai': 'Сан Сай и Дой Сакет', 'east': 'Сан Кампхэнг, Сарапхи, Мае Он', 'further': 'Дальше от города' },
    allAreas: 'Все районы', osm: 'Районы: © участники OpenStreetMap.',
    all: 'Все', allCities: 'Все города', found: n => `Найдено: ${n}`,
    empty: 'Ничего не найдено. Попробуйте другое слово или уберите фильтры.',
    link: 'Ссылка', date: 'Дата', regular: 'регулярно', hours: 'Время', price: 'Цена', contacts: 'Контакты',
    map: 'На карте', mapN: n => `Карта ${n}`, post: 'Пост', postMore: n => `Пост (ещё ${n})`, hide: 'Скрыть пост',
    openTg: 'Открыть в Telegram', morePosts: n => `Ещё посты (${n})`, frameTitle: 'Пост канала',
    foot: (n, d) => `Записей: ${n}. По постам канала до ${d}.`,
    loadError: 'Не удалось загрузить каталог. Обновите страницу.',
    fmtDate: iso => { const [y, m, d] = iso.split('-'); return `${d}.${m}.${y}`; },
  },
  en: {
    channel: 'my_chiangmai_en',
    home: 'Chiang Mai',
    cats: {
      food_cafe: 'Cafes', food_restaurant: 'Restaurants', food_bar: 'Bars',
      food_bakery: 'Bakeries & desserts', food_products: 'Groceries', shopping_market: 'Markets',
      shopping_store: 'Shops', kids: 'Kids', health: 'Health', beauty_relax: 'Massage & spa',
      sport_practice: 'Sport & yoga', services: 'Services', housing: 'Housing & hotels',
      work_study: 'Work & study', leisure: 'Leisure & nature', music_venues: 'Live music',
      events: 'Events', travel: 'Trips', info: 'Good to know', community: 'Communities',
    },
    areas: { 'old-city': 'Old City', 'nimman': 'Nimman & Suthep', 'santitham': 'Santitham & Chang Phueak', 'riverside': 'Tha Phae & riverside', 'south': 'South of the city', 'mae-hia': 'Mae Hia', 'northeast': 'North-east of the city', 'hang-dong': 'Hang Dong', 'mae-rim': 'Mae Rim', 'san-sai': 'San Sai & Doi Saket', 'east': 'San Kamphaeng, Saraphi, Mae On', 'further': 'Further out' },
    allAreas: 'All areas', osm: 'Areas: © OpenStreetMap contributors.',
    all: 'All', allCities: 'All cities', found: n => `Found: ${n}`,
    empty: 'Nothing found. Try another word or clear the filters.',
    link: 'Link', date: 'Date', regular: 'regular', hours: 'Hours', price: 'Price', contacts: 'Contacts',
    map: 'Map', mapN: n => `Map ${n}`, post: 'Post', postMore: n => `Post (+${n} more)`, hide: 'Hide post',
    openTg: 'Open in Telegram', morePosts: n => `More posts (${n})`, frameTitle: 'Channel post',
    foot: (n, d) => `${n} entries, from the channel's posts up to ${d}.`,
    loadError: 'Could not load the catalog. Reload the page.',
    fmtDate: iso => { const [y, m, d] = iso.split('-'); return `${MONTHS[m - 1]} ${+d}, ${y}`; },
  },
};
const T = STRINGS[SITE.lang] || STRINGS.ru;
const CATS = T.cats;
const PAGE = 30;
const tg = window.Telegram && window.Telegram.WebApp;
const inTelegram = !!(tg && tg.initData);
if (inTelegram) { tg.ready(); tg.expand(); }

const $ = id => document.getElementById(id);
const norm = s => (s || '').toLowerCase().replace(/ё/g, 'е');
const pad = n => String(n).padStart(2, '0');
const now = new Date();
const TODAY = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;

let items = [], view = [], shown = 0;
const state = { q: '', cat: '', city: '', area: '', past: false };

function readHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  state.q = p.get('q') || ''; state.cat = CATS[p.get('c')] ? p.get('c') : '';
  state.city = p.get('city') || ''; state.past = p.get('past') === '1';
  state.area = T.areas[p.get('area')] ? p.get('area') : '';
}
function writeHash() {
  const p = new URLSearchParams();
  if (state.q) p.set('q', state.q);
  if (state.cat) p.set('c', state.cat);
  if (state.city) p.set('city', state.city);
  if (state.area) p.set('area', state.area);
  if (state.past) p.set('past', '1');
  const h = p.toString();
  history.replaceState(null, '', h ? '#' + h : location.pathname + location.search);
  // The other language keeps the category, the area and the past-events switch; words and city names differ.
  const o = new URLSearchParams();
  if (state.cat) o.set('c', state.cat);
  if (state.area) o.set('area', state.area);
  if (state.past) o.set('past', '1');
  $('lang').href = SITE.other + (o.toString() ? '#' + o : '');
}

const isPast = it => it.k === 'event' && !it.r && (!it.ed || it.ed < TODAY);

function matches(it, tokens, withCat) {
  if (withCat && state.cat && it.c !== state.cat) return false;
  if (state.city && it.city !== state.city) return false;
  if (state.area && it.z !== state.area) return false;
  if (it.k === 'event') {
    if (!state.past && isPast(it)) return false;
    if (!tokens.length && state.cat !== 'events') return false;
  }
  return tokens.every(t => it._hay.includes(t));
}
function score(it, tokens) {
  let s = 0;
  for (const t of tokens) s += it._name.includes(t) ? 3 : it._key.includes(t) ? 2 : 1;
  return s;
}

// The area filter belongs to the home city: it shows with the home city or with all cities.
function syncArea() {
  const on = !state.city || state.city === T.home;
  if (!on) state.area = '';
  $('area').hidden = !on;
  $('search').classList.toggle('two', on);
  $('area').value = state.area;
}

function apply() {
  syncArea();
  const tokens = norm(state.q).split(/\s+/).filter(Boolean);
  const counts = {};
  let total = 0;
  for (const it of items) if (matches(it, tokens, false)) { counts[it.c] = (counts[it.c] || 0) + 1; total++; }
  view = items.filter(it => matches(it, tokens, true));
  if (state.cat === 'events' && !tokens.length) {
    // Dated upcoming events first (soonest on top), then regular ones, then past (latest on top).
    const rank = it => it.ed && it.ed >= TODAY ? 0 : it.r ? 1 : 2;
    view.sort((a, b) => rank(a) - rank(b) || (rank(a) === 0
      ? a.ed.localeCompare(b.ed)
      : rank(a) === 1 ? b.last.localeCompare(a.last) : (b.ed || '').localeCompare(a.ed || '')));
  } else if (tokens.length) {
    view.sort((a, b) => score(b, tokens) - score(a, tokens) || b.last.localeCompare(a.last));
  }
  renderChips(counts, total, tokens.length > 0);
  $('pastWrap').hidden = !(state.cat === 'events' || tokens.length);
  $('count').textContent = view.length ? T.found(view.length) : '';
  $('list').replaceChildren();
  shown = 0;
  if (!view.length) {
    const e = document.createElement('div');
    e.className = 'empty';
    e.textContent = T.empty;
    $('list').append(e);
  }
  more();
  writeHash();
}

function renderChips(counts, total, searching) {
  const box = $('chips');
  box.replaceChildren();
  const add = (key, label, n) => {
    const b = document.createElement('button');
    b.className = 'chip'; b.type = 'button';
    b.setAttribute('aria-pressed', String(state.cat === key));
    b.append(label);
    const c = document.createElement('small'); c.textContent = n; b.append(c);
    b.onclick = () => { state.cat = state.cat === key ? '' : key; apply(); window.scrollTo(0, 0); };
    box.append(b);
  };
  add('', T.all, total);
  for (const key of Object.keys(CATS)) {
    const n = counts[key] || 0;
    if (n || state.cat === key || (key === 'events' && !searching)) add(key, CATS[key], n || '');
  }
}

function linkLabel(url) {
  try {
    const h = new URL(url).hostname.replace(/^www\./, '');
    if (h.includes('instagram.')) return 'Instagram';
    if (h.includes('facebook.') || h === 'fb.com' || h === 'fb.me') return 'Facebook';
    if (h === 't.me') return 'Telegram';
    if (h.includes('line.me') || h === 'lin.ee') return 'LINE';
    return h;
  } catch (e) { return T.link; }
}
function anchor(url, label, primary) {
  const a = document.createElement('a');
  a.className = primary ? 'btn primary' : 'btn';
  a.href = url; a.target = '_blank'; a.rel = 'noopener';
  a.textContent = label;
  if (inTelegram) a.onclick = ev => {
    ev.preventDefault();
    if (/^https:\/\/t\.me\//.test(url)) tg.openTelegramLink(url); else tg.openLink(url);
  };
  return a;
}
function contact(c) {
  if (/^@[A-Za-z0-9_]{4,}$/.test(c)) return anchor('https://t.me/' + c.slice(1), c);
  const s = document.createElement('span'); s.textContent = c; return s;
}

// Posts open inside the card through Telegram's public post embed, which needs no Telegram account or app.
const MAPS = /^https?:\/\/(maps\.app\.goo\.gl|goo\.gl\/maps|(www\.)?google\.[a-z.]+\/maps|maps\.google\.[a-z.]+)/;

const postUrl = id => `https://t.me/${T.channel}/${id}`;
function postFrame(id) {
  const dark = inTelegram ? tg.colorScheme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  const f = document.createElement('iframe');
  f.src = `${postUrl(id)}?embed=1${dark ? '&dark=1' : ''}`;
  f.title = T.frameTitle; f.loading = 'lazy'; f.setAttribute('scrolling', 'no');
  return f;
}
window.addEventListener('message', e => {
  // The embed reports its height as JSON: {"event": "resize", "height": ...}.
  if (e.origin !== 'https://t.me') return;
  let d;
  try { d = JSON.parse(e.data); } catch (_) { return; }
  if (!d || d.event !== 'resize' || !d.height) return;
  for (const f of document.querySelectorAll('.embed iframe')) {
    if (f.contentWindow === e.source) { f.style.height = d.height + 'px'; break; }
  }
});
function postButton(it, box) {
  const label = it.ids.length > 1 ? T.postMore(it.ids.length - 1) : T.post;
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'btn primary'; b.textContent = label;
  b.setAttribute('aria-expanded', 'false');
  const toggle = () => {
    if (!box.childElementCount) {
      box.append(postFrame(it.ids[0]));
      const row = document.createElement('div'); row.className = 'row';
      // A long post pushes the top button off a phone screen, so the post gets its own Hide button below it.
      const hide = document.createElement('button');
      hide.type = 'button'; hide.className = 'btn'; hide.textContent = T.hide;
      hide.onclick = toggle;
      row.append(hide, anchor(postUrl(it.ids[0]), T.openTg));
      const rest = it.ids.slice(1);
      if (rest.length) {
        const m = document.createElement('button');
        m.type = 'button'; m.className = 'btn'; m.textContent = T.morePosts(rest.length);
        m.onclick = () => { for (const id of rest) row.before(postFrame(id)); m.remove(); };
        row.append(m);
      }
      box.append(row);
    }
    const open = box.hidden;
    box.hidden = !open;
    b.textContent = open ? T.hide : label;
    b.setAttribute('aria-expanded', String(open));
    if (!open) {
      // After hiding, bring the card back into view instead of leaving the reader further down the list.
      const card = b.closest('.card');
      if (card && card.getBoundingClientRect().top < 0) card.scrollIntoView({ block: 'start' });
    }
  };
  b.onclick = toggle;
  return b;
}

function card(it) {
  const el = document.createElement('article');
  el.className = 'card';
  const h = document.createElement('h2'); h.textContent = it.n; el.append(h);
  const sub = document.createElement('div'); sub.className = 'sub';
  const place = it.a || T.areas[it.z];
  sub.textContent = [it.s || CATS[it.c], place, it.city !== T.home || !place ? it.city : null].filter(Boolean).join(' · ');
  el.append(sub);
  if (it.d) { const p = document.createElement('p'); p.textContent = it.d; el.append(p); }
  const facts = [];
  if (it.k === 'event' && it.r) facts.push([T.date, it.ed && it.ed >= TODAY ? T.fmtDate(it.ed) + ', ' + T.regular : T.regular]);
  else if (it.k === 'event' && it.ed) facts.push([T.date, T.fmtDate(it.ed)]);
  if (it.h) facts.push([T.hours, it.h]);
  if (it.p) facts.push([T.price, it.p]);
  if (facts.length) {
    const ul = document.createElement('ul'); ul.className = 'facts';
    for (const [k, v] of facts) {
      const li = document.createElement('li'); const b = document.createElement('b');
      b.textContent = k + ': '; li.append(b, v); ul.append(li);
    }
    el.append(ul);
  }
  if (it.ct && it.ct.length) {
    const ul = document.createElement('ul'); ul.className = 'facts';
    const li = document.createElement('li'); const b = document.createElement('b'); b.textContent = T.contacts + ': ';
    li.append(b);
    it.ct.forEach((c, i) => { if (i) li.append(', '); li.append(contact(c)); });
    ul.append(li); el.append(ul);
  }
  if (it.t && it.t.length) {
    const tags = document.createElement('div'); tags.className = 'tags';
    for (const t of it.t) {
      const b = document.createElement('button'); b.className = 'tag'; b.type = 'button'; b.textContent = t;
      b.onclick = () => { state.q = t; state.cat = ''; $('q').value = t; apply(); window.scrollTo(0, 0); };
      tags.append(b);
    }
    el.append(tags);
  }
  const act = document.createElement('div'); act.className = 'actions';
  const box = document.createElement('div'); box.className = 'embed'; box.hidden = true;
  // The post is the main action; the map is the main one only for an item without a post.
  const hasPost = !!(T.channel && it.ids && it.ids.length);
  if (hasPost) act.append(postButton(it, box));
  // Routes and trips can have several map points: the main one is "Map", the others "Map 2", "Map 3".
  const maps = [it.m, ...(it.l || []).filter(u => MAPS.test(u))].filter(Boolean);
  maps.forEach((u, i) => act.append(anchor(u, i ? T.mapN(i + 1) : T.map, !hasPost && !i)));
  for (const u of (it.l || []).filter(u => !MAPS.test(u))) act.append(anchor(u, linkLabel(u)));
  if (act.children.length) el.append(act);
  el.append(box);
  return el;
}

function more() {
  const frag = document.createDocumentFragment();
  for (const it of view.slice(shown, shown + PAGE)) frag.append(card(it));
  shown = Math.min(view.length, shown + PAGE);
  $('list').append(frag);
}
new IntersectionObserver(es => { if (es[0].isIntersecting && shown < view.length) more(); }, { rootMargin: '600px' }).observe($('more'));

let timer;
$('q').addEventListener('input', e => { clearTimeout(timer); timer = setTimeout(() => { state.q = e.target.value.trim(); apply(); }, 150); });
$('city').addEventListener('change', e => { state.city = e.target.value; apply(); });
$('area').addEventListener('change', e => { state.area = e.target.value; apply(); });
$('past').addEventListener('change', e => { state.past = e.target.checked; apply(); });

window.addEventListener('hashchange', () => {
  readHash();
  $('q').value = state.q; $('past').checked = state.past;
  $('city').value = state.city; if ($('city').value !== state.city) state.city = '';
  apply();
});

fetch(SITE.data).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(data => {
  items = data.items;
  const cities = {}, areas = {};
  for (const it of items) {
    it._name = norm(it.n);
    it._key = norm([it.s, (it.t || []).join(' '), CATS[it.c]].join(' '));
    it._hay = [it._name, it._key, norm(it.d), norm(it.a), norm(it.city), norm(T.areas[it.z])].join(' ');
    cities[it.city] = (cities[it.city] || 0) + 1;
    if (it.z) areas[it.z] = (areas[it.z] || 0) + 1;
  }
  const asel = $('area');
  asel.append(new Option(T.allAreas, ''));
  for (const [id, name] of Object.entries(T.areas)) if (areas[id]) asel.append(new Option(`${name} (${areas[id]})`, id));
  const sel = $('city');
  sel.append(new Option(T.allCities, ''));
  Object.entries(cities).filter(([, n]) => n >= 5).sort((a, b) => b[1] - a[1])
    .forEach(([c, n]) => sel.append(new Option(`${c} (${n})`, c)));
  readHash();
  $('q').value = state.q; $('past').checked = state.past;
  sel.value = state.city; if (sel.value !== state.city) state.city = '';
  $('foot').textContent = T.foot(items.length, T.fmtDate(data.built_from_posts_until)) + ' ' + T.osm;
  apply();
}).catch(() => {
  const e = document.createElement('div'); e.className = 'empty';
  e.textContent = T.loadError;
  $('list').append(e);
});
