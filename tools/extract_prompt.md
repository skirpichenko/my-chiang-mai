# Extraction spec: posts → catalog entries

You are building a searchable catalog from a Russian-language Telegram channel about life in Chiang Mai, Thailand (the channel also covers other Thai cities and trips). The channel history is split into plain-text part files. Your job: turn every post of lasting value in YOUR part files into structured catalog entries.

The caller gives you a list of pairs: an input part file (`.txt`) and the output file to write (`.jsonl`). Process them one at a time, in the order given.

Each post in a part file looks like:

```
=== #<post_id> | <YYYY-MM-DD> [| reply_to=#<id>] [| fwd=<source>]
<post text; hidden links are rendered as: label <url>>
```

## Procedure, per part file
1. Read the WHOLE file with the Read tool. If the output is truncated, keep reading with offset until you reach the end. Do not skim: consider every post.
2. Write the entries for that part to its `.jsonl` output file with the Write tool: one JSON object per line, UTF-8, no markdown fences, no trailing commas, no blank-line padding. If the part has nothing worth an entry, still write an empty file (that marks the part as done).
3. Validate it: `python3 -I -c "import json,sys; n=sum(1 for l in open(sys.argv[1]) if l.strip() and json.loads(l)); print(n)" <output path>` — fix the file if it fails.
4. Only then move on to the next part file. Finish all parts.

## What becomes an entry
One entry per DISTINCT place / business / specialist / service / event / useful-info topic.
- A post listing 10 cafes with 10 map links => 10 entries, each with its own maps_url. Never collapse a list into one entry.
- The same place mentioned in several posts of the same part => ONE entry with all post ids in post_ids.
- kind="place": cafes, restaurants, bars, markets, shops, malls, clinics, spas, parks, temples, hotels, schools, coworkings, playgrounds, venues, etc.
- kind="service": people or companies offering a service without it being a destination (cleaner, plumber, driver, visa agent, tutor, photographer, delivery, masseur at home, yoga teacher, etc.).
- kind="event": a dated event announcement (concert, festival, workshop, class session). Fill event_date (ISO date; take the year from the post date when the post gives only day/month), put the venue in "area"/summary and the venue map link in maps_url if present, and set recurring=true for weekly/regular events. Do NOT also emit a separate place entry for the venue unless the post actually describes the venue itself.
- kind="info": posts with lasting practical value that are not a single place: guides, how-tos, rules, visa/immigration/transport/banking/health tips, seasonal advice (smoke season, rainy season), emergency contacts, price overviews, lists of useful chats/channels.
- SKIP (no entry): greetings, jokes, polls, pure chatter, memes, reposted one-day weather/traffic/news items with no lasting value, and short follow-ups that carry no information of their own. A reply_to follow-up that adds a fact to a post inside the same part should be merged into that post's entry (add its id to post_ids).

## Entry fields (all keys present in every object; use null or [] when unknown)
```
{
 "kind": "place" | "service" | "event" | "info",
 "name": string — exact name as written in the post (keep Latin/Thai spelling; for info entries a short Russian title),
 "category": one of the slugs below,
 "subcategory": short Russian free text, e.g. "стоматология", "веганское кафе", "ночной рынок", "уборка",
 "summary": Russian, 1-2 concrete sentences, max 300 chars: what it is and what the post says is notable about it. No marketing fluff, no emoji,
 "city": "Чиангмай" by default; otherwise the actual city/province in Russian (e.g. "Чианграй", "Пай", "Бангкок", "Хуахин"),
 "area": district / neighbourhood / mall if stated (e.g. "Нимман", "Хангдонг", "Мае Рим", "Старый город", "Сантитам"), else null,
 "maps_url": the Google Maps link copied VERBATIM (full URL including query string), else null,
 "links": [other URLs from the post: website, Instagram, Facebook, LINE, booking, Telegram channel],
 "contacts": [phones, @telegram handles, emails, LINE ids exactly as written],
 "price": price info as stated (string) or null,
 "hours": opening hours / schedule as stated (string) or null,
 "tags": 2-6 lowercase Russian search keywords a newcomer might type (e.g. "декаф", "с детьми", "веган", "бесплатно", "живая музыка", "русскоязычный", "доставка"),
 "post_ids": [integer post ids this entry is based on],
 "event_date": "YYYY-MM-DD" or null (events only),
 "recurring": true | false | null (events only)
}
```

## Category slugs (use exactly one)
- food_cafe — кафе, кофейни, завтраки
- food_restaurant — рестораны, уличная еда, кухни мира
- food_bar — бары, руфтопы, ночная жизнь
- food_bakery — пекарни, десерты, шоколад, мороженое
- food_products — продукты, фермы, органика, доставка еды, алкоголь/вино
- shopping_market — рынки, ярмарки, блошиные рынки
- shopping_store — магазины, ТЦ, одежда, секонд-хенд, винтаж, косметика, товары для дома, техника, ремесло
- kids — всё для детей: площадки, развлечения, школы, сады, кружки, лагеря, няни
- health — клиники, стоматология, анализы, врачи, аптеки, психологи, ветеринары
- beauty_relax — массаж, спа, сауна, онсен, салоны красоты, парикмахеры
- sport_practice — йога, медитации, ретриты, танцы, бассейны, спортзалы, единоборства, спорт
- services — уборка, ремонт, мастера, водители, трансфер, аренда транспорта, визы, юристы, переводчики, страхование, фотографы, доставка, связь, банки
- housing — отели, гестхаусы, аренда жилья, кондо, риелторы
- work_study — коворкинги, курсы, языковые школы, обучение для взрослых
- leisure — парки, природа, водопады, прогулки, храмы, музеи, галереи, искусство, достопримечательности, кино, мастер-классы как место
- music_venues — площадки с живой музыкой, джаз, концертные залы
- events — афиша: конкретное событие с датой
- travel — поездки и места ЗА пределами Чиангмая и окрестностей (другие города/провинции), маршруты
- info — полезная информация, гайды, правила, новости с долгой ценностью
- community — чаты, каналы, сообщества, клубы по интересам

Use "travel" only for kind="info" route/trip overviews; a cafe in Chiang Rai is still food_cafe with city="Чианграй".

## Rules
- Only facts that are in the post text. Never invent addresses, prices, hours, links or names. Unknown => null / [].
- Copy URLs, phones and handles verbatim.
- Do not translate or transliterate place names.
- Write only the output files you were given. Do not modify anything else.

When all parts are done, report for each part file: its path, how many posts it contained, how many entries you wrote, and whether the JSONL validated; plus short notes on anything ambiguous.
