#!/usr/bin/env python3
"""Turn the datasets in results/data/ into one HTML report per stay period.

Each report lists every bookable accommodation for its period, sorted by
price, and links across to the other periods. Also regenerates
results/reports.json, the manifest the Pages index is built from.

Usage: python3 tools/build_report.py
"""
import datetime
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "results" / "data"
OUT = ROOT / "results"
PHOTO_DIR = "assets/photos"
FONT_URL = "assets/fraunces-600.woff2"

# The stay the family asked for. Only Saturday-to-Saturday is bookable, so no
# period matches it exactly; each one is scored against this below.
WISH_FROM = datetime.date(2026, 10, 19)
WISH_TO = datetime.date(2026, 11, 1)

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember"]

# Facility keys the API knows, in the order they should appear as chips.
CHIP_ORDER = ["nonsmoking", "activityroom", "seaview", "stove", "dishwasher",
              "washer", "dryer", "internet", "sauna", "whirlpool", "jacuzzi",
              "pool", "extra-toilet", "heatpump", "ev-charger", "luxury"]
CHIP_LABEL = {
    "nonsmoking": "Nichtraucher", "activityroom": "Aktivitätsraum",
    "seaview": "Meerblick", "stove": "Kaminofen", "dishwasher": "Geschirrspüler",
    "washer": "Waschmaschine", "dryer": "Trockner", "internet": "Internet",
    "sauna": "Sauna", "whirlpool": "Whirlpool", "jacuzzi": "Jacuzzi",
    "pool": "Pool", "extra-toilet": "Extra Toilette", "heatpump": "Wärmepumpe",
    "ev-charger": "E-Ladestecker", "luxury": "Luxus",
}
KID_FACILITIES = {"activityroom", "pool"}


def esc(s):
    return html.escape(s or "", quote=True)


def money(v):
    return f"{v:,.0f}".replace(",", ".")


def d(iso):
    return datetime.date.fromisoformat(iso)


def short(iso):
    x = d(iso)
    return f"{WEEKDAYS[x.weekday()]} {x.day}.{x.month}."


def long_date(iso):
    x = d(iso)
    return f"{WEEKDAYS[x.weekday()]} {x.day}. {MONTHS[x.month - 1]} {x.year}"


def period_title(arrival, departure):
    """'17.–31. Oktober 2026', but spelled out on both sides when the period
    crosses a month boundary."""
    a, b = d(arrival), d(departure)
    if a.month == b.month and a.year == b.year:
        return f"Fanø {a.day}.–{b.day}. {MONTHS[b.month - 1]} {b.year}"
    return (f"Fanø {a.day}. {MONTHS[a.month - 1]} – "
            f"{b.day}. {MONTHS[b.month - 1]} {b.year}")


def is_house(rec):
    """Danibo types some Golfstien flats as 'House'. Their address carries the
    Danish 'lejl.' (lejlighed = flat) and the description calls them
    Ferienwohnung, so trust that over the type field."""
    if re.search(r"lejl\.", rec["address"], re.I):
        return False
    return rec["type"] == "House"


def coverage(arrival, departure):
    """How this period relates to the stay the family actually wanted.

    Returns (kind, sentence). The sentence carries no trailing period so
    callers can punctuate it themselves.
    """
    a, b = d(arrival), d(departure)
    wish = f"{WISH_FROM.day}.{WISH_FROM.month}. – {WISH_TO.day}.{WISH_TO.month}."
    if a <= WISH_FROM and b >= WISH_TO:
        return "full", f"Deckt den Wunsch {wish} vollständig ab"
    parts = []
    if a > WISH_FROM:
        parts.append(f"beginnt erst am {a.day}.{a.month}.")
    if b < WISH_TO:
        parts.append(f"endet schon am {b.day}.{b.month}.")
    sentence = " und ".join(parts)
    return "partial", f"Gegenüber dem Wunsch {wish}: {sentence}"


def sentence(text):
    """German dates end in a period, so only add one where it is missing."""
    return text if text.endswith(".") else text + "."


def excerpt(text, limit=340):
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    dot = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[:dot + 1] if dot > 160 else cut.rstrip() + " …"


def stars(rating, count):
    if not count:
        return '<span class="rating"><span class="none">noch keine Bewertung</span></span>'
    full = int(round(rating))
    return (f'<span class="rating"><span class="stars">{"★" * full}{"☆" * (5 - full)}</span>'
            f'{rating:.2f} · {count} Bewertung{"en" if count != 1 else ""}</span>')


def dist(m):
    if m is None:
        return "–"
    if m == 0:
        return "am Ort"
    return f"{m/1000:.1f} km".replace(".", ",") if m >= 1000 else f"{m} m"


CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  --ground:#E7EAE6; --surface:#F8F9F6; --surface-2:#EFF2ED;
  --ink:#17201D; --ink-2:#586661; --ink-3:#7C8A85;
  --line:#CBD2CB; --line-soft:#DDE3DC;
  --accent:#1E5A5E; --accent-ink:#123C40; --accent-soft:#D6E3E2; --on-accent:#F8F9F6;
  --warm:#8F4526; --warm-soft:#F0DFD6;
  --straw:#9A7A2E;
  --shadow:0 1px 2px rgba(23,32,29,.06), 0 8px 24px -16px rgba(23,32,29,.35);
  --radius:3px;
  --display:'Fraunces','Iowan Old Style','Palatino Linotype',Palatino,Georgia,serif;
  --body:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
  --mono:ui-monospace,SFMono-Regular,'SF Mono','DejaVu Sans Mono',Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#0E1513; --surface:#151E1B; --surface-2:#1B2622;
    --ink:#E4EAE5; --ink-2:#9CAAA4; --ink-3:#7B8983;
    --line:#2A3733; --line-soft:#222E2A;
    --accent:#7FBDBC; --accent-ink:#A9D6D4; --accent-soft:#1B3A3A; --on-accent:#0E1513;
    --warm:#DE8B65; --warm-soft:#3A2419;
    --straw:#CFA854;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 30px -18px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"]{
  --ground:#0E1513; --surface:#151E1B; --surface-2:#1B2622;
  --ink:#E4EAE5; --ink-2:#9CAAA4; --ink-3:#7B8983;
  --line:#2A3733; --line-soft:#222E2A;
  --accent:#7FBDBC; --accent-ink:#A9D6D4; --accent-soft:#1B3A3A; --on-accent:#0E1513;
  --warm:#DE8B65; --warm-soft:#3A2419;
  --straw:#CFA854;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 30px -18px rgba(0,0,0,.8);
}
html{-webkit-text-size-adjust:100%}
body{margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--body); font-size:16px; line-height:1.55}
.wrap{max-width:1080px; margin:0 auto; padding:0 24px}
a{color:var(--accent); text-underline-offset:2px}
a:focus-visible,button:focus-visible,select:focus-visible{
  outline:2px solid var(--accent); outline-offset:2px; border-radius:2px}

.masthead{border-bottom:1px solid var(--line); background:var(--surface)}
.masthead .wrap{padding-top:40px; padding-bottom:32px}
.eyebrow{font-family:var(--mono); font-size:11px; letter-spacing:.16em;
  text-transform:uppercase; color:var(--ink-3); margin:0 0 16px}
.eyebrow a{color:var(--ink-3)}
.eyebrow b{color:var(--accent); font-weight:600}
h1{font-family:var(--display); font-weight:600; font-size:clamp(28px,4.6vw,46px);
  line-height:1.06; letter-spacing:-.015em; margin:0 0 10px; text-wrap:balance}
.dek{margin:0; max-width:62ch; color:var(--ink-2); font-size:17px}
.brief{display:grid; gap:1px; background:var(--line-soft); border:1px solid var(--line-soft);
  grid-template-columns:repeat(auto-fit,minmax(168px,1fr)); margin-top:28px}
.brief div{background:var(--surface); padding:13px 15px}
.brief dt{font-family:var(--mono); font-size:10.5px; letter-spacing:.13em;
  text-transform:uppercase; color:var(--ink-3); margin:0 0 5px}
.brief dd{margin:0; font-size:15px; font-weight:600; line-height:1.35}
.brief dd small{display:block; font-weight:400; color:var(--ink-2);
  font-size:12.5px; margin-top:2px}

.note{border-left:3px solid var(--warm); background:var(--warm-soft);
  padding:16px 20px; margin:0 0 18px; border-radius:0 var(--radius) var(--radius) 0}
.note.calm{border-left-color:var(--accent); background:var(--accent-soft)}
.note h3{font-family:var(--body); font-size:14px; font-weight:700; margin:0 0 6px}
.note p{margin:0 0 8px; font-size:14.5px; color:var(--ink); max-width:74ch}
.note p:last-child{margin-bottom:0}
.note code{font-family:var(--mono); font-size:12.5px; background:var(--surface);
  padding:1px 5px; border-radius:2px; border:1px solid var(--line-soft)}

section{padding:38px 0}
section.tight{padding-top:28px}
h2{font-family:var(--display); font-weight:600; font-size:clamp(21px,3vw,28px);
  margin:0 0 6px; letter-spacing:-.01em; text-wrap:balance}
.section-note{margin:0 0 22px; color:var(--ink-2); font-size:15px; max-width:70ch}

.spans{display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(228px,1fr))}
.span{background:var(--surface); border:1px solid var(--line); padding:16px 17px;
  border-radius:var(--radius); display:flex; flex-direction:column}
.span.here{border-color:var(--accent); box-shadow:inset 0 0 0 1px var(--accent)}
.span .tag{font-family:var(--mono); font-size:10px; letter-spacing:.13em;
  text-transform:uppercase; color:var(--ink-3); display:block; margin-bottom:7px}
.span.here .tag{color:var(--accent)}
.span .dates{font-size:16px; font-weight:700; margin-bottom:3px}
.span .dates a{color:inherit; text-decoration:none}
.span .dates a:hover{color:var(--accent); text-decoration:underline}
.span .meta{font-size:13px; color:var(--ink-2); margin-bottom:11px}
.span .stat{font-family:var(--mono); font-size:13px; font-variant-numeric:tabular-nums}
.span .stat b{font-size:18px; font-weight:600}
.span .cover{font-size:12.5px; margin:10px 0 0; padding-top:10px;
  border-top:1px dashed var(--line); color:var(--ink-2)}
.span .cover.full{color:var(--accent-ink); font-weight:600}

.controls{position:sticky; top:0; z-index:20; background:var(--ground);
  border-bottom:1px solid var(--line); padding:11px 0;
  backdrop-filter:saturate(140%) blur(6px)}
.controls .wrap{display:flex; flex-wrap:wrap; gap:9px; align-items:center}
.ctl{font-family:var(--mono); font-size:12px; letter-spacing:.05em;
  text-transform:uppercase; color:var(--ink-2); background:var(--surface);
  border:1px solid var(--line); padding:7px 12px; border-radius:100px;
  cursor:pointer; transition:background .15s,color .15s,border-color .15s}
.ctl:hover{border-color:var(--accent)}
.ctl[aria-pressed="true"]{background:var(--accent); border-color:var(--accent);
  color:var(--on-accent)}
select.ctl{text-transform:none; letter-spacing:0; padding-right:26px}
.count{margin-left:auto; font-family:var(--mono); font-size:12px; color:var(--ink-3);
  font-variant-numeric:tabular-nums}

.list{display:flex; flex-direction:column; gap:16px; padding:26px 0 10px}
.card{display:grid; grid-template-columns:296px 1fr; background:var(--surface);
  border:1px solid var(--line); border-radius:var(--radius); overflow:hidden;
  box-shadow:var(--shadow)}
.card.hide{display:none}
.gallery{background:var(--surface-2); border-right:1px solid var(--line-soft);
  display:grid; grid-template-rows:1fr auto; min-height:260px}
.gallery .hero{display:block; width:100%; height:100%; min-height:200px;
  object-fit:cover; background:var(--surface-2)}
.gallery .strip{display:grid; grid-template-columns:repeat(4,1fr); gap:1px;
  background:var(--line-soft)}
.gallery .strip img{display:block; width:100%; aspect-ratio:1/1; object-fit:cover;
  background:var(--surface-2)}
.gallery .noimg{aspect-ratio:4/3; display:grid; place-items:center; color:var(--ink-3);
  font-family:var(--mono); font-size:11px; letter-spacing:.1em; text-transform:uppercase}
.body{padding:18px 22px 20px; min-width:0}
.head{display:flex; gap:14px; align-items:flex-start; flex-wrap:wrap}
.rank{font-family:var(--mono); font-size:12px; color:var(--ink-3);
  border:1px solid var(--line); border-radius:100px; padding:2px 9px;
  font-variant-numeric:tabular-nums; flex:none; margin-top:3px}
.titleblock{flex:1 1 220px; min-width:0}
.titleblock h3{font-family:var(--display); font-weight:600; font-size:21px;
  margin:0 0 2px; letter-spacing:-.008em; line-height:1.2}
.titleblock h3 a{color:inherit; text-decoration:none}
.titleblock h3 a:hover{color:var(--accent)}
.addr{margin:0; font-size:13.5px; color:var(--ink-2)}
.addr .kat{font-family:var(--mono); font-size:11.5px; color:var(--ink-3)}
.price{text-align:right; flex:none}
.price .total{font-family:var(--mono); font-size:25px; font-weight:600;
  color:var(--warm); font-variant-numeric:tabular-nums; line-height:1.1; display:block}
.price .per{font-size:12px; color:var(--ink-2); font-family:var(--mono);
  font-variant-numeric:tabular-nums}
.rating{display:inline-flex; align-items:center; gap:5px; font-size:13px;
  color:var(--ink-2); margin-top:6px}
.rating .stars{color:var(--straw); letter-spacing:1px; font-size:12px}
.rating .none{color:var(--ink-3); font-style:italic}
.specs{display:grid; grid-template-columns:repeat(4,1fr); gap:1px;
  background:var(--line-soft); border:1px solid var(--line-soft); margin:15px 0 13px}
.specs div{background:var(--surface); padding:8px 10px}
.specs dt{font-family:var(--mono); font-size:9.5px; letter-spacing:.1em;
  text-transform:uppercase; color:var(--ink-3); margin:0 0 2px}
.specs dd{margin:0; font-size:14px; font-weight:600; font-variant-numeric:tabular-nums}
.chips{display:flex; flex-wrap:wrap; gap:5px; margin:0 0 12px}
.chip{font-size:11.5px; padding:2.5px 8px; border-radius:100px;
  background:var(--surface-2); border:1px solid var(--line-soft); color:var(--ink-2)}
.chip.type{background:var(--accent-soft); border-color:transparent;
  color:var(--accent-ink); font-weight:600}
.chip.ns{background:var(--accent); border-color:transparent; color:var(--on-accent);
  font-weight:600}
.chip.ns-unknown{background:transparent; border-style:dashed; color:var(--ink-3)}
.desc{font-size:14.5px; color:var(--ink-2); margin:0 0 14px; max-width:68ch}
.actions{display:flex; flex-wrap:wrap; gap:9px; align-items:center}
.btn{display:inline-block; font-size:13.5px; font-weight:600; text-decoration:none;
  padding:8px 15px; border-radius:100px; background:var(--accent);
  color:var(--on-accent); transition:filter .15s}
.btn:hover{filter:brightness(1.12)}
.btn.ghost{background:transparent; border:1px solid var(--line); color:var(--ink-2)}
.btn.ghost:hover{border-color:var(--accent); color:var(--accent)}
.altprices{font-family:var(--mono); font-size:12px; color:var(--ink-2);
  margin:12px 0 0; padding-top:11px; border-top:1px dashed var(--line);
  font-variant-numeric:tabular-nums}
.altprices b{color:var(--ink); font-weight:600}
.altprices a{white-space:nowrap; margin-right:14px; display:inline-block;
  text-decoration:none}
.altprices a:hover{text-decoration:underline}

.tablewrap{overflow-x:auto; border:1px solid var(--line);
  border-radius:var(--radius); background:var(--surface)}
table{border-collapse:collapse; width:100%; font-size:13.5px; min-width:760px}
th,td{padding:9px 12px; text-align:left; border-bottom:1px solid var(--line-soft)}
th{font-family:var(--mono); font-size:10px; letter-spacing:.1em; text-transform:uppercase;
  color:var(--ink-3); font-weight:400; background:var(--surface-2); position:sticky; top:0}
td.num{text-align:right; font-family:var(--mono); font-variant-numeric:tabular-nums}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:var(--surface-2)}
td a{text-decoration:none; font-weight:600}
td a:hover{text-decoration:underline}

footer{border-top:1px solid var(--line); background:var(--surface); margin-top:36px}
footer .wrap{padding:34px 24px 46px}
footer h2{font-size:19px; margin-bottom:14px}
footer p{font-size:14px; color:var(--ink-2); max-width:76ch; margin:0 0 12px}
pre{font-family:var(--mono); font-size:12.5px; line-height:1.65;
  background:var(--surface-2); border:1px solid var(--line-soft);
  border-radius:var(--radius); padding:14px 16px; overflow-x:auto; margin:0 0 14px;
  color:var(--ink)}
.legend{list-style:none; padding:0; margin:0 0 14px; font-size:14px; color:var(--ink-2)}
.legend li{margin-bottom:6px; padding-left:16px; position:relative}
.legend li::before{content:"—"; position:absolute; left:0; color:var(--ink-3)}

@media (max-width:820px){
  .card{grid-template-columns:1fr}
  .gallery{border-right:none; border-bottom:1px solid var(--line-soft);
    min-height:0; grid-template-rows:auto auto}
  .gallery .hero{aspect-ratio:16/9; height:auto; min-height:0}
  .specs{grid-template-columns:repeat(2,1fr)}
  .price{text-align:left}
  .wrap{padding:0 18px}
}
@media (prefers-reduced-motion:reduce){
  *{transition:none!important; animation:none!important; scroll-behavior:auto!important}
}
"""


def spec(label, value):
    return f"<div><dt>{label}</dt><dd>{value}</dd></div>"


def card(rank, rec, period_files):
    house = is_house(rec)
    typ = "Ferienhaus" if house else "Ferienwohnung"
    facilities = set(rec.get("facilities") or ())
    nights = rec["nights"]
    per_night = rec["totalPrice"] / nights if nights else 0
    photos = rec.get("photoFiles") or []

    if photos:
        strip = "".join(f'<img src="{PHOTO_DIR}/{esc(p)}" alt="" loading="lazy">'
                        for p in photos[1:])
        gal = (f'<img class="hero" src="{PHOTO_DIR}/{esc(photos[0])}" '
               f'alt="{esc(typ)} {esc(rec["name"])}, {esc(rec["location"])}" loading="lazy">'
               + (f'<div class="strip">{strip}</div>' if strip else ""))
    else:
        gal = '<div class="noimg">kein Bild</div>'

    if "nonsmoking" in facilities:
        ns = '<span class="chip ns">Nichtraucher</span>'
    else:
        ns = '<span class="chip ns-unknown">Keine Angabe zum Rauchen</span>'
    chips = [f'<span class="chip type">{typ}</span>', ns]
    chips += [f'<span class="chip">{CHIP_LABEL[k]}</span>'
              for k in CHIP_ORDER if k in facilities and k != "nonsmoking"]

    specs = "".join([
        spec("Personen", rec["maxPersons"]),
        spec("Schlafz.", rec["bedrooms"]),
        spec("Bäder", rec["bathrooms"]),
        spec("Wohnfläche", f'{rec["squareMeters"]} m²'),
        spec("Baujahr", rec["buildYear"] or "–"),
        spec("Zum Strand", dist(rec["distanceToCoastM"])),
        spec("Einkauf", dist(rec["distanceToStoreM"])),
        spec("Haustiere", rec["maxPets"] or "nein"),
    ])

    others = rec.get("otherPeriods") or {}
    altp = ""
    if others:
        parts = []
        for key in sorted(others, key=lambda k: (d(k.split(":")[0]), d(k.split(":")[1]))):
            arr, dep = key.split(":")
            parts.append(f'<a href="{period_files[key]}#h{rec["id"]}">'
                         f'{short(arr)}–{short(dep)} <b>{money(others[key])} €</b></a>')
        altp = f'<p class="altprices">Andere Zeiträume: {"".join(parts)}</p>'

    maps = f'https://www.google.com/maps/search/?api=1&query={rec["latitude"]},{rec["longitude"]}'
    kid = len(facilities & KID_FACILITIES)

    return f"""
<article class="card" id="h{rec['id']}" data-type="{'house' if house else 'apartment'}"
         data-ns="{1 if 'nonsmoking' in facilities else 0}"
         data-price="{rec['totalPrice']:.0f}" data-sqm="{rec['squareMeters']}"
         data-coast="{rec['distanceToCoastM']}" data-rating="{rec['rating']}"
         data-kid="{kid}">
  <div class="gallery">{gal}</div>
  <div class="body">
    <div class="head">
      <span class="rank">{rank:02d}</span>
      <div class="titleblock">
        <h3><a href="{esc(rec['url'])}" target="_blank" rel="noopener">{esc(rec['address'])}</a></h3>
        <p class="addr">{esc(rec['location'])}, Fanø <span class="kat">· Kat.-Nr. {esc(rec['name'])}</span></p>
        {stars(rec['rating'], rec['ratingCount'])}
      </div>
      <div class="price">
        <span class="total">{money(rec['totalPrice'])}&nbsp;€</span>
        <span class="per">{money(per_night)} € / Nacht · {nights} Nächte</span>
      </div>
    </div>
    <dl class="specs">{specs}</dl>
    <div class="chips">{"".join(chips)}</div>
    <p class="desc">{esc(excerpt(rec.get('description')))}</p>
    <div class="actions">
      <a class="btn" href="{esc(rec['url'])}" target="_blank" rel="noopener">Auf danibo.dk ansehen</a>
      <a class="btn ghost" href="{maps}" target="_blank" rel="noopener">Lage auf der Karte</a>
    </div>
    {altp}
  </div>
</article>"""


def table_row(rank, rec):
    facilities = set(rec.get("facilities") or ())
    return f"""<tr>
<td class="num">{rank:02d}</td>
<td><a href="{esc(rec['url'])}" target="_blank" rel="noopener">{esc(rec['address'])}</a></td>
<td>{esc(rec['location'])}</td>
<td>{'Haus' if is_house(rec) else 'Wohnung'}</td>
<td class="num">{rec['maxPersons']}</td>
<td class="num">{rec['bedrooms']}</td>
<td class="num">{rec['squareMeters']}</td>
<td class="num">{dist(rec['distanceToCoastM'])}</td>
<td>{'ja' if 'nonsmoking' in facilities else 'k. A.'}</td>
<td class="num">{money(rec['totalPrice'])} €</td>
</tr>"""


def span_card(ds, here, period_files):
    key = f"{ds['arrival']}:{ds['departure']}"
    kind, note = coverage(ds["arrival"], ds["departure"])
    prices = [h["totalPrice"] for h in ds["houses"] if h["totalPrice"]]
    dates = f"{short(ds['arrival'])} → {short(ds['departure'])}"
    label = (dates if here
             else f'<a href="{period_files[key]}">{dates}</a>')
    return f"""<div class="span{' here' if here else ''}">
  <span class="tag">{'Dieser Bericht' if here else 'Anderer Zeitraum'}</span>
  <div class="dates">{label}</div>
  <div class="meta">{ds['nights']} Nächte</div>
  <div class="stat"><b>{len(ds['houses'])}</b> Objekte · ab <b>{money(min(prices))} €</b></div>
  <p class="cover{' full' if kind == 'full' else ''}">{note}</p>
</div>"""


def build(ds, datasets, period_files):
    key = f"{ds['arrival']}:{ds['departure']}"
    houses = ds["houses"]
    nights = ds["nights"]
    n_house = sum(1 for h in houses if is_house(h))
    n_ns = sum(1 for h in houses if "nonsmoking" in (h.get("facilities") or ()))
    prices = [h["totalPrice"] for h in houses if h["totalPrice"]]
    kind, cover_note = coverage(ds["arrival"], ds["departure"])
    title = period_title(ds["arrival"], ds["departure"])

    spans = "".join(span_card(other, other is ds, period_files)
                    for other in datasets)
    cards = "".join(card(i, h, period_files) for i, h in enumerate(houses, 1))
    rows = "".join(table_row(i, h) for i, h in enumerate(houses, 1))

    cover_line = sentence(cover_note)

    return f"""<title>{esc(title)}</title>
<style>@font-face{{font-family:'Fraunces';font-style:normal;font-weight:600;
font-display:swap;src:url({FONT_URL}) format('woff2');}}{CSS}</style>

<header class="masthead">
  <div class="wrap">
    <p class="eyebrow"><a href="index.html">Übersicht</a> · <b>Danibo</b> · Fanø, Dänemark</p>
    <h1>{esc(title)}</h1>
    <p class="dek">Alle {len(houses)} bei Danibo buchbaren Unterkünfte von
    {long_date(ds['arrival'])} bis {long_date(ds['departure'])} für zwei Erwachsene
    und zwei Kinder (8 und 11 Jahre) — nach Gesamtpreis sortiert, mit Ausstattung,
    Lage, Nichtraucher-Status und Bildern.</p>

    <dl class="brief">
      <div><dt>Zeitraum</dt><dd>{short(ds['arrival'])} – {short(ds['departure'])}<small>{nights} Nächte</small></dd></div>
      <div><dt>Belegung</dt><dd>2 Erw. + 2 Kinder<small>8 und 11 Jahre, keine Haustiere</small></dd></div>
      <div><dt>Treffer</dt><dd>{len(houses)} Objekte<small>{n_house} Häuser · {len(houses) - n_house} Wohnungen</small></dd></div>
      <div><dt>Preisspanne</dt><dd>{money(min(prices))} – {money(max(prices))} €<small>Gesamt inkl. Nebenkosten</small></dd></div>
      <div><dt>Nichtraucher</dt><dd>{n_ns} von {len(houses)}<small>laut Danibo-Merkmal</small></dd></div>
    </dl>
  </div>
</header>

<section class="tight">
  <div class="wrap">
    <div class="note{' calm' if kind == 'full' else ''}">
      <h3>Warum dieser Zeitraum?</h3>
      <p>Danibo vermietet auf Fanø in dieser Saison ausschließlich <strong>samstags bis
      samstags</strong> — geprüft über <code>danibo.py availability</code>: im Oktober und
      November 2026 gibt es keine einzige Anreise an einem anderen Wochentag. Der Wunsch
      „19.10. bis 1.11.“ ist deshalb nicht buchbar; jede Suche darauf liefert null Treffer.</p>
      <p>{cover_line} Es gibt vier buchbare Samstag-zu-Samstag-Varianten, jede mit einem
      eigenen vollständigen Bericht — unten verlinkt. Bei jedem Objekt stehen außerdem
      seine Preise in den anderen Zeiträumen.</p>
    </div>
    <div class="note calm">
      <h3>Nichtraucher: {n_ns} der {len(houses)} Objekte</h3>
      <p>Danibo führt „Nichtraucher“ als eigenes Suchmerkmal, gesetzt bei {n_ns} der
      {len(houses)} hier verfügbaren Unterkünfte — Häuser wie Wohnungen. „Rauchen erlaubt“
      ist bei keinem Objekt hinterlegt.</p>
      <p>Die Liste ist deshalb nicht hart gefiltert, sondern zeigt den Status als Kennzeichen.
      Wo „keine Angabe“ steht, fehlt schlicht das gepflegte Merkmal — hier lohnt eine kurze
      Rückfrage bei Danibo. Der Schalter <em>Nur Nichtraucher</em> grenzt auf die bestätigten
      Objekte ein.</p>
    </div>
  </div>
</section>

<section class="tight">
  <div class="wrap">
    <h2>Die vier buchbaren Zeiträume</h2>
    <p class="section-note">Alle mit denselben Belegungsdaten geprüft. Die Zahl nennt
    buchbare Objekte, der Preis den günstigsten Gesamtpreis.</p>
    <div class="spans">{spans}</div>
  </div>
</section>

<div class="controls">
  <div class="wrap">
    <button class="ctl" id="f-house" aria-pressed="false">Nur Häuser</button>
    <button class="ctl" id="f-ns" aria-pressed="false">Nur Nichtraucher</button>
    <button class="ctl" id="f-kid" aria-pressed="false">Pool / Aktivitätsraum</button>
    <select class="ctl" id="sort" aria-label="Sortierung">
      <option value="price">Sortierung: Preis aufsteigend</option>
      <option value="price-desc">Sortierung: Preis absteigend</option>
      <option value="sqm">Sortierung: Wohnfläche</option>
      <option value="coast">Sortierung: Strandnähe</option>
      <option value="rating">Sortierung: Bewertung</option>
    </select>
    <span class="count" id="count"></span>
  </div>
</div>

<section style="padding-top:0">
  <div class="wrap"><div class="list" id="list">{cards}</div></div>
</section>

<section class="tight">
  <div class="wrap">
    <h2>Alles auf einen Blick</h2>
    <p class="section-note">Dieselben {len(houses)} Objekte, {nights} Nächte,
    Gesamtpreis in Euro inklusive Endreinigung und Buchungsgebühr.</p>
    <div class="tablewrap">
      <table>
        <thead><tr>
          <th>#</th><th>Adresse</th><th>Ort</th><th>Typ</th><th>Pers.</th><th>SZ</th>
          <th>m²</th><th>Strand</th><th>Nichtraucher</th><th>Gesamt</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </div>
</section>

<footer>
  <div class="wrap">
    <h2>Wie diese Liste entstanden ist</h2>
    <p>Erhoben mit dem CLI-Tool <code>danibo.py</code> aus diesem Repository, das die
    öffentliche JSON-API von danibo.dk abfragt — dieselbe Schnittstelle, die auch die
    Website-Suche bedient. Reproduzierbar mit:</p>
    <pre>./danibo.py search --arrival {ds['arrival']} --departure {ds['departure']} \\
    --adults 2 --children 2 --sort price \\
    --with-photos --resolve-facilities --json</pre>
    <ul class="legend">
      <li>Preise in Euro von der deutschen Seitenversion, Gesamtpreis inklusive
      Pflichtnebenkosten (Endreinigung, Buchungsgebühr) und abzüglich Rabatten — dieselbe
      Zahl, die die Website anzeigt. Strom und Wasser rechnet Danibo separat bei Abreise ab.</li>
      <li>Der exakt buchbare Betrag in DKK lässt sich pro Haus mit
      <code>./danibo.py quote &lt;id&gt; --arrival … --departure …</code> abrufen.</li>
      <li>Ausstattungsmerkmale kommen aus der API. Fünf davon — darunter „Nichtraucher“ —
      gibt die Suche nicht pro Haus zurück; <code>--resolve-facilities</code> holt sie über
      je einen zusätzlichen gefilterten Suchlauf. Nicht jedes Merkmal ist bei Danibo gepflegt:
      „Grill“, „Terrasse“ und „eingezäunt“ sind fast überall leer, obwohl die
      Beschreibungstexte sie nennen. Fehlendes Merkmal heißt also nicht zwingend
      „nicht vorhanden“.</li>
      <li>Haus oder Wohnung stammt aus dem Feld <code>type</code> der Suchergebnisse — mit
      einer Korrektur: einzelne Golfstien-Objekte sind dort als Haus geführt, tragen aber
      „lejl.“ (dänisch <em>lejlighed</em> = Wohnung) in der Adresse und heißen im
      Beschreibungstext Ferienwohnung. Sie stehen hier als Wohnung.</li>
      <li>Die Suche liefert nur tatsächlich buchbare Zeiträume — jedes gelistete Objekt war
      zum Erhebungszeitpunkt frei. Verfügbarkeit und Preise können sich ändern; vor der
      Buchung auf danibo.dk gegenprüfen.</li>
    </ul>
  </div>
</footer>

<script>
(function () {{
  var list = document.getElementById('list');
  var cards = Array.prototype.slice.call(list.children);
  var state = {{ house: false, ns: false, kid: false, sort: 'price' }};
  function num(el, key) {{ return parseFloat(el.dataset[key]) || 0; }}
  var sorters = {{
    'price':      function (a, b) {{ return num(a, 'price') - num(b, 'price'); }},
    'price-desc': function (a, b) {{ return num(b, 'price') - num(a, 'price'); }},
    'sqm':        function (a, b) {{ return num(b, 'sqm') - num(a, 'sqm'); }},
    'coast':      function (a, b) {{ return num(a, 'coast') - num(b, 'coast'); }},
    'rating':     function (a, b) {{ return num(b, 'rating') - num(a, 'rating'); }}
  }};
  function apply() {{
    var shown = 0;
    cards.forEach(function (c) {{
      var ok = true;
      if (state.house && c.dataset.type !== 'house') ok = false;
      if (state.ns && c.dataset.ns !== '1') ok = false;
      if (state.kid && num(c, 'kid') < 1) ok = false;
      c.classList.toggle('hide', !ok);
      if (ok) shown++;
    }});
    cards.slice().sort(sorters[state.sort]).forEach(function (c) {{ list.appendChild(c); }});
    document.getElementById('count').textContent =
      shown + ' von ' + cards.length + ' Objekten';
  }}
  function toggle(id, key) {{
    var btn = document.getElementById(id);
    btn.addEventListener('click', function () {{
      state[key] = !state[key];
      btn.setAttribute('aria-pressed', String(state[key]));
      apply();
    }});
  }}
  toggle('f-house', 'house');
  toggle('f-ns', 'ns');
  toggle('f-kid', 'kid');
  document.getElementById('sort').addEventListener('change', function (e) {{
    state.sort = e.target.value;
    apply();
  }});
  apply();
}})();
</script>"""


def main():
    files = sorted(DATA.glob("*.json"))
    if not files:
        sys.exit(f"error: no datasets in {DATA} — run tools/fetch_report_data.py first")
    datasets = [json.loads(p.read_text(encoding="utf-8")) for p in files]
    datasets.sort(key=lambda x: (d(x["arrival"]), d(x["departure"])))

    period_files = {f"{x['arrival']}:{x['departure']}":
                    f"fanoe-{x['arrival']}_{x['departure']}.html" for x in datasets}

    manifest = []
    for ds in datasets:
        key = f"{ds['arrival']}:{ds['departure']}"
        name = period_files[key]
        (OUT / name).write_text(build(ds, datasets, period_files), encoding="utf-8")

        houses = ds["houses"]
        prices = [h["totalPrice"] for h in houses if h["totalPrice"]]
        n_house = sum(1 for h in houses if is_house(h))
        n_ns = sum(1 for h in houses if "nonsmoking" in (h.get("facilities") or ()))
        kind, note = coverage(ds["arrival"], ds["departure"])
        manifest.append({
            "file": name,
            "title": period_title(ds["arrival"], ds["departure"]),
            "date": "2026-08-16",
            "stay": f"{long_date(ds['arrival'])} – {long_date(ds['departure'])}, "
                    f"{ds['nights']} Nächte",
            "summary": f"Alle {len(houses)} buchbaren Unterkünfte für 2 Erwachsene und "
                       f"2 Kinder, nach Preis sortiert — mit Fotos, Ausstattung, Lage "
                       f"und Nichtraucher-Status. {sentence(note)}",
            "facts": [
                f"{len(houses)} Objekte · {n_house} Häuser, {len(houses) - n_house} Wohnungen",
                f"{money(min(prices))} – {money(max(prices))} € gesamt inkl. Nebenkosten",
                f"{n_ns} mit Nichtraucher-Merkmal",
            ],
            "highlight": kind == "full",
            "data": f"data/{ds['arrival']}_{ds['departure']}.json",
        })
        print(f"  {name}  {len(houses)} Objekte")

    (OUT / "reports.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote results/reports.json ({len(manifest)} reports)")


if __name__ == "__main__":
    main()
