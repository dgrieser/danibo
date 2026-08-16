#!/usr/bin/env python3
"""Collect everything a report needs for one or more stay periods.

Runs the search per period, pulls each house's German description, and
downloads a hero image plus a few thumbnails per house into shared assets —
the periods overlap heavily, so the photos are fetched once and reused by
every report that mentions the house.

Writes results/data/<arrival>_<departure>.json per period.

Usage: python3 tools/fetch_report_data.py 2026-10-17:2026-10-31 [more...]
"""
import base64
import concurrent.futures
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import danibo  # noqa: E402

DATA = ROOT / "results" / "data"
PHOTOS = ROOT / "results" / "assets" / "photos"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
HERO_W, THUMB_W, N_THUMBS = 560, 240, 4
ADULTS, CHILDREN = 2, 2


def search(client, arrival, departure):
    kwargs = dict(arrival=arrival, departure=departure, adults=ADULTS,
                  children=CHILDREN, page_size=100, max_pages=5)
    hits, _, meta = danibo.search_houses(client, **kwargs)
    hidden = danibo.resolve_facilities(client, danibo.HIDDEN_FACILITIES, kwargs)
    records = []
    for h in hits:
        rec = danibo.simplify_house(h, meta["currency"], hidden.get(h["id"], ()))
        rec["photos"] = danibo.get_house_photos(client, rec["id"], size="Large")
        records.append(rec)
    records.sort(key=lambda r: (r["totalPrice"] is None, r["totalPrice"], r["name"]))
    return records, meta


def description(client, house_id):
    det = danibo.get_house_details(client, house_id)
    de = [t for t in det.get("translations") or [] if t.get("language") == "DE"]
    raw = de[0]["description"] if de else ""
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text).strip()


def resized(url, width):
    if "bookingstudio.dk" in url:
        return re.sub(r"/\d+-auto/", f"/{width}-auto/", url)
    if "nordsee-holidays.de" in url or "cloudinary" in url:
        return re.sub(r"h_\d+,w_\d+", f"h_{round(width * 0.75)},w_{width}", url)
    return url


def download(url, width, dest):
    if dest.exists() and dest.stat().st_size:
        return dest.name
    for attempt in range(3):
        try:
            req = urllib.request.Request(resized(url, width), headers=UA)
            with urllib.request.urlopen(req, timeout=45) as resp:
                blob = resp.read()
            if blob:
                dest.write_bytes(blob)
                return dest.name
        except Exception as exc:
            if attempt == 2:
                print(f"    image failed {dest.name}: {exc}", file=sys.stderr)
    return None


def fetch_photos(records_by_id):
    """One hero and up to N_THUMBS thumbnails per house, shared across periods."""
    PHOTOS.mkdir(parents=True, exist_ok=True)
    jobs = []
    for hid, rec in records_by_id.items():
        photos = rec.get("photos") or ([rec["thumbnail"]] if rec.get("thumbnail") else [])
        for i, url in enumerate(photos[:1 + N_THUMBS]):
            width = HERO_W if i == 0 else THUMB_W
            jobs.append((hid, i, url, width, PHOTOS / f"{hid}-{i}.jpg"))

    got = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(download, url, w, dest): (hid, i)
                   for hid, i, url, w, dest in jobs}
        for fut in concurrent.futures.as_completed(futures):
            hid, i = futures[fut]
            name = fut.result()
            if name:
                got.setdefault(hid, {})[i] = name
    return {hid: [names[k] for k in sorted(names)] for hid, names in got.items()}


def main():
    periods = []
    for arg in sys.argv[1:]:
        if ":" not in arg:
            sys.exit(f"error: expected arrival:departure, got '{arg}'")
        periods.append(tuple(arg.split(":", 1)))
    if not periods:
        sys.exit(__doc__)

    DATA.mkdir(parents=True, exist_ok=True)
    client = danibo.ApiClient()

    collected = {}
    for arrival, departure in periods:
        print(f"searching {arrival} -> {departure}")
        records, meta = search(client, arrival, departure)
        print(f"  {len(records)} houses")
        collected[(arrival, departure)] = (records, meta)

    by_id = {}
    for records, _ in collected.values():
        for rec in records:
            by_id.setdefault(rec["id"], rec)
    print(f"{len(by_id)} distinct houses across {len(periods)} period(s)")

    print("fetching descriptions")
    descriptions = {}
    for hid in by_id:
        try:
            descriptions[hid] = description(client, hid)
        except danibo.ApiError as exc:
            print(f"  details failed for {hid}: {exc}", file=sys.stderr)
            descriptions[hid] = ""

    print("downloading photos")
    photo_files = fetch_photos(by_id)
    print(f"  {sum(len(v) for v in photo_files.values())} files in {PHOTOS}")

    # Cross-period prices, so each report can show what the other weeks cost.
    others = {}
    for (arrival, departure), (records, _) in collected.items():
        for rec in records:
            others.setdefault(rec["id"], {})[f"{arrival}:{departure}"] = rec["totalPrice"]

    for (arrival, departure), (records, meta) in collected.items():
        for rec in records:
            rec["description"] = descriptions.get(rec["id"], "")
            rec["photoFiles"] = photo_files.get(rec["id"], [])
            rec["otherPeriods"] = {k: v for k, v in others.get(rec["id"], {}).items()
                                   if k != f"{arrival}:{departure}"}
            rec.pop("photos", None)
        out = DATA / f"{arrival}_{departure}.json"
        out.write_text(json.dumps({
            "arrival": arrival, "departure": departure,
            "adults": ADULTS, "children": CHILDREN,
            "nights": records[0]["nights"] if records else None,
            "currency": meta["currency"],
            "totalMatches": meta["totalHouses"],
            "houses": records,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)}  ({len(records)} houses)")


if __name__ == "__main__":
    main()
