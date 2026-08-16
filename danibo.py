#!/usr/bin/env python3
"""danibo.py — CLI to search holiday houses/accommodations on https://www.danibo.dk/de/ (Fanø, Denmark).

Uses the same JSON API that powers the site's own search and extended search
("Erweiterte Suche"). No HTML scraping, no authentication required.

Endpoints used (all public, read-only GET):
  /api/search                      house search incl. all extended-search filters
  /api/house/{id}                  full house details (description, translations, ...)
  /api/house/{id}/media            photo URLs
  /api/period                      exact price quote for a stay (incl. mandatory products)
  /api/period/availabilities       bookable arrival/departure combinations

Designed to be usable by humans and by AI agents (--json output, --cheapest).
Stdlib only — no third-party dependencies. Python 3.8+.
"""

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://www.danibo.dk"
AGENCY_ID = 9  # danibo's agency id on the bookingstudio platform (from site config)
USER_AGENT = "danibo-cli/1.0 (+https://github.com/dgrieser/danibo; polite scraper, throttled)"

# Locations on Fanø, taken from the site's Angular config.
LOCATIONS = {
    "rindby": [46],
    "fanoe-bad": [44],
    "soenderho": [47],
    "nordby": [45],
}

# House types from the site's Angular config ("houseType" query parameter).
HOUSE_TYPES = {
    "house": 1,     # Ferienhaus
    "hotel": 2,     # Hotel
    "camping": 3,   # Camping
    "tent": 4,      # Hütte
}

# Facility ids from the site's Angular config ("features" query parameter).
# Keys are CLI-friendly; German UI label in the comment.
FACILITIES = {
    "washer": 14,        # Waschmaschine
    "dishwasher": 12,    # Geschirrspülmaschine
    "pool": 17,          # Pool
    "whirlpool": 19,     # Whirlpool (Spa)
    "sauna": 18,         # Sauna
    "seaview": 28,       # Meerblick
    "stove": 13,         # Brennofen
    "internet": 9,       # Internet
    "nonsmoking": 27,    # Nichtraucher-Haus
    "ev-charger": 20,    # Ladestecker für Elektroautos (Typ 2)
    "heatpump": 31,      # Wärmepumpe
    "activityroom": 21,  # Aktivitätsraum
    "extra-toilet": 51,  # Extra Toilette / Bad
    "luxury": 47,        # Luxus Ferienhäuser
}

# language code -> numeric languageId used by /api/period
LANGUAGE_IDS = {"de": 1, "da": 2}
# The site shows EUR for the German version and DKK for the Danish one.
LANGUAGE_CURRENCY = {"de": "EUR", "da": "DKK"}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --------------------------------------------------------------------------
# HTTP client: throttled, retrying, caching
# --------------------------------------------------------------------------

class ApiClient:
    """Polite HTTP client for the danibo API.

    - enforces a minimum interval between requests (with jitter) to avoid
      hammering the server / triggering rate limits
    - retries transient failures (429, 5xx, network errors) with exponential
      backoff, honouring a Retry-After header when present
    - caches GET responses on disk with a TTL so repeated invocations
      (e.g. an AI agent polling for prices) don't re-hit the server
    """

    def __init__(self, throttle=0.8, retries=4, timeout=30,
                 cache_dir=None, cache_ttl=900, cache_enabled=True, verbose=False):
        self.throttle = throttle
        self.retries = retries
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.cache_enabled = cache_enabled
        self.verbose = verbose
        self._last_request = 0.0
        if cache_dir is None:
            base = os.environ.get("XDG_CACHE_HOME", os.path.join(os.path.expanduser("~"), ".cache"))
            cache_dir = os.path.join(base, "danibo-cli")
        self.cache_dir = cache_dir

    def _log(self, msg):
        if self.verbose:
            print(f"[danibo] {msg}", file=sys.stderr)

    def _cache_path(self, url):
        return os.path.join(self.cache_dir, hashlib.sha256(url.encode()).hexdigest() + ".json")

    def _cache_get(self, url, ttl):
        if ttl <= 0:
            return None
        path = self._cache_path(url)
        try:
            if time.time() - os.path.getmtime(path) < ttl:
                with open(path, "r", encoding="utf-8") as fh:
                    self._log(f"cache hit: {url}")
                    return json.load(fh)
        except (OSError, ValueError):
            pass
        return None

    def _cache_put(self, url, data):
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            path = self._cache_path(url)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            os.replace(tmp, path)
        except OSError:
            pass  # caching is best-effort

    def _wait_turn(self):
        elapsed = time.monotonic() - self._last_request
        min_gap = self.throttle + random.uniform(0, self.throttle * 0.25)
        if elapsed < min_gap:
            time.sleep(min_gap - elapsed)

    def get_json(self, path, params=None, cache_ttl=None):
        """GET a JSON document from the API with throttle/retry/cache."""
        url = BASE_URL + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=False)
        ttl = self.cache_ttl if cache_ttl is None else cache_ttl
        if not self.cache_enabled:
            ttl = 0

        cached = self._cache_get(url, ttl)
        if cached is not None:
            return cached

        delay = 2.0
        last_error = None
        for attempt in range(1, self.retries + 2):
            self._wait_turn()
            self._log(f"GET {url} (attempt {attempt})")
            req = urllib.request.Request(url, headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
                "Accept-Language": "de,en;q=0.8",
            })
            self._last_request = time.monotonic()
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    body = resp.read()
                data = json.loads(body.decode("utf-8"))
                self._cache_put(url, data)
                return data
            except urllib.error.HTTPError as exc:
                last_error = f"HTTP {exc.code} for {url}"
                if exc.code in (429, 500, 502, 503, 504) and attempt <= self.retries:
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    wait = delay
                    if retry_after:
                        try:
                            wait = max(wait, float(retry_after))
                        except ValueError:
                            pass
                    self._log(f"{last_error}, retrying in {wait:.1f}s")
                    time.sleep(wait + random.uniform(0, 1))
                    delay *= 2
                    continue
                raise ApiError(f"{last_error}: {exc.reason}") from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt <= self.retries:
                    self._log(f"{last_error}, retrying in {delay:.1f}s")
                    time.sleep(delay + random.uniform(0, 1))
                    delay *= 2
                    continue
                raise ApiError(f"request failed after {attempt} attempts: {last_error}") from exc
        raise ApiError(f"request failed: {last_error}")


class ApiError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# API operations
# --------------------------------------------------------------------------

def search_houses(client, arrival, departure, adults=2, children=0, pets=0,
                  locations=None, facilities=None, house_type=None,
                  bedrooms=1, bathrooms=1, max_price=0, min_sqm=0,
                  min_build_year=0, max_distance_coast=0, max_distance_store=0,
                  max_distance_town=0, flexible=False, keyword=None,
                  language="de", page_size=50, max_pages=None):
    """Query /api/search across all result pages. Returns (houses, meta)."""
    houses = []
    alternatives = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        params = {
            "agencyId": AGENCY_ID,
            "language": language,
            "persons": adults + children,
            "month": 0,
            "pets": pets,
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "distanceToCoast": max_distance_coast,
            "distanceToStore": max_distance_store,
            "distanceToTown": max_distance_town,
            "squareMeters": min_sqm,
            "buildYear": min_build_year,
            "createdLastDays": 0,
            "price": max_price,
            "sortBy": 0,
            "page": page,
            "pageSize": page_size,
            "fastSearch": "false",
        }
        if locations:
            ids = []
            for loc in locations:
                ids.extend(LOCATIONS[loc])
            params["locations"] = ",".join(str(i) for i in ids)
        if keyword:
            params["keyword"] = re.sub(r"['\"{}()]", "", keyword)
        if house_type:
            params["houseType"] = HOUSE_TYPES[house_type]
        if arrival:
            params["arrival"] = arrival
        if departure:
            params["departure"] = departure
        if flexible:
            params["flexibleArrival"] = "true"
        if facilities:
            params["features"] = ",".join(str(FACILITIES[f]) for f in facilities)

        data = client.get_json("/api/search", params)
        houses.extend(data.get("houses") or [])
        alternatives.extend(data.get("alternativeHouses") or [])
        total_pages = data.get("totalPages") or 1
        if max_pages and page >= max_pages:
            break
        page += 1

    meta = {
        "totalHouses": data.get("totalHouses"),
        "totalAlternativeHouses": data.get("totalAlternativeHouses"),
        "currency": LANGUAGE_CURRENCY.get(language, "EUR"),
        "arrival": arrival,
        "departure": departure,
    }
    return houses, alternatives, meta


def get_house_details(client, house_id, language="de"):
    # House master data changes rarely; cache for a day.
    return client.get_json(f"/api/house/{house_id}", {"language": language}, cache_ttl=86400)


def get_house_photos(client, house_id, size="Medium", language="de"):
    """Return list of photo URLs. size: Small | Medium | Large."""
    lang_id = LANGUAGE_IDS.get(language, 1)
    media = client.get_json(f"/api/house/{house_id}/media",
                            {"size": size, "type": "Default", "language": lang_id},
                            cache_ttl=86400)
    return [m["url"] for m in media if m.get("url")]


def get_quote(client, house_id, arrival, departure, adults=2, pets=0, language="de"):
    """Exact price quote (in DKK, incl. mandatory products) via /api/period."""
    lang_id = LANGUAGE_IDS.get(language, 1)
    return client.get_json("/api/period", {
        "houseId": house_id,
        "arrival": arrival,
        "departure": departure,
        "languageId": lang_id,
        "adults": adults,
        "pets": pets,
    }, cache_ttl=300)


def get_availabilities(client, house_id, date_from=None, date_to=None):
    """Bookable (arrival, departure) pairs for a house."""
    params = {"houseId": house_id}
    if date_from:
        params["from"] = date_from
    if date_to:
        params["to"] = date_to
    pairs = client.get_json("/api/period/availabilities", params, cache_ttl=300)
    return [{"arrival": p["item1"], "departure": p["item2"]} for p in pairs]


# --------------------------------------------------------------------------
# Output formatting
# --------------------------------------------------------------------------

def house_url(house_id, arrival=None, departure=None):
    """Detail-page URL on the German site, same format the site's own cards use."""
    url = f"{BASE_URL}/de/s/ferienhaus/?id={house_id}"
    if arrival and departure:
        url += f"&start={arrival}&end={departure}"
    return url


def simplify_house(h, currency):
    """Reduce a raw search hit to a stable, AI-friendly record."""
    facilities = sorted(k for k, v in {
        "internet": h.get("internet"), "dishwasher": h.get("dishWasher"),
        "stove": h.get("stove"), "washer": h.get("washer"),
        "dryer": h.get("dryer"), "whirlpool": h.get("jacuzzi"),
        "pool": h.get("pool"), "sauna": h.get("sauna"), "spa": h.get("spa"),
        "ev-charger": h.get("chargerType2"), "activityroom": h.get("houseActivity"),
    }.items() if v)
    return {
        "id": h.get("id"),
        "name": h.get("name"),
        "type": h.get("type"),
        "address": h.get("address"),
        "location": h.get("location"),
        "url": house_url(h.get("id"), (h.get("arrival") or "")[:10],
                         (h.get("departure") or "")[:10]),
        "latitude": h.get("latitude"),
        "longitude": h.get("longitude"),
        "rating": h.get("rating"),
        "ratingCount": h.get("ratingCount"),
        "summary": h.get("summary"),
        "thumbnail": h.get("thumbnail"),
        "maxPersons": h.get("maxPersons"),
        "maxPets": h.get("maxPets"),
        "bedrooms": h.get("bedrooms"),
        "bathrooms": h.get("bathrooms"),
        "squareMeters": h.get("squareMeters"),
        "buildYear": h.get("buildYear"),
        "distanceToCoastM": h.get("distanceToCoast"),
        "distanceToStoreM": h.get("distanceToStore"),
        "facilities": facilities,
        "available": True,  # /api/search only returns bookable periods
        "arrival": (h.get("arrival") or "")[:10],
        "departure": (h.get("departure") or "")[:10],
        "nights": h.get("duration"),
        "currency": currency,
        "rentPrice": h.get("price"),
        "mandatoryProductsPrice": h.get("productsPrice"),
        "discount": h.get("discount"),
        "totalPrice": h.get("priceWithDiscount"),
        "tags": h.get("tags"),
    }


def print_house_text(rec, index=None):
    head = f"{rec['name']} ({rec['type']}, id {rec['id']})"
    if index is not None:
        head = f"#{index}  " + head
    print(head)
    print(f"    {rec['address']}, {rec['location']}  |  {rec['url']}")
    bits = [
        f"{rec['maxPersons']} persons", f"{rec['bedrooms']} bedrooms",
        f"{rec['bathrooms']} bathrooms", f"{rec['squareMeters']} m²",
    ]
    if rec.get("maxPets"):
        bits.append(f"{rec['maxPets']} pets allowed")
    if rec.get("buildYear"):
        bits.append(f"built {rec['buildYear']}")
    print("    " + ", ".join(bits))
    print(f"    beach {rec['distanceToCoastM']} m, shopping {rec['distanceToStoreM']} m"
          + (f", rating {rec['rating']}/5 ({rec['ratingCount']})" if rec.get("rating") else ""))
    if rec.get("facilities"):
        print("    facilities: " + ", ".join(rec["facilities"]))
    print(f"    {rec['arrival']} → {rec['departure']} ({rec['nights']} nights): "
          f"{rec['totalPrice']:.2f} {rec['currency']} total "
          f"(rent {rec['rentPrice']:.2f} + mandatory extras {rec['mandatoryProductsPrice']:.2f}"
          + (f", discount -{rec['discount']:.2f}" if rec.get("discount") else "") + ")")
    if rec.get("summary"):
        print(f"    {rec['summary']}")
    if rec.get("photos"):
        print("    photos:")
        for url in rec["photos"]:
            print(f"      {url}")
    print()


# --------------------------------------------------------------------------
# CLI commands
# --------------------------------------------------------------------------

def check_date(value):
    if not DATE_RE.match(value):
        raise argparse.ArgumentTypeError(f"invalid date '{value}', expected YYYY-MM-DD")
    return value


def cmd_search(args, client):
    if bool(args.arrival) != bool(args.departure):
        sys.exit("error: --arrival and --departure must be given together")
    houses, alternatives, meta = search_houses(
        client,
        arrival=args.arrival, departure=args.departure,
        adults=args.adults, children=args.children, pets=args.pets,
        locations=args.location or None, facilities=args.facility or None,
        house_type=args.type, bedrooms=args.bedrooms, bathrooms=args.bathrooms,
        max_price=args.max_price, min_sqm=args.min_sqm,
        min_build_year=args.min_build_year,
        max_distance_coast=args.max_distance_coast,
        max_distance_store=args.max_distance_store,
        flexible=args.flexible, keyword=args.keyword,
        language=args.language, page_size=args.page_size,
        max_pages=args.max_pages,
    )
    currency = meta["currency"]
    records = [simplify_house(h, currency) for h in houses]

    sort_keys = {
        "price": lambda r: (r["totalPrice"] is None, r["totalPrice"]),
        "rating": lambda r: -(r["rating"] or 0),
        "size": lambda r: -(r["squareMeters"] or 0),
        "beach": lambda r: (r["distanceToCoastM"] is None, r["distanceToCoastM"]),
    }
    records.sort(key=sort_keys[args.sort])
    if args.cheapest:
        records = records[:args.cheapest]
    if args.limit:
        records = records[:args.limit]

    if args.with_photos:
        for rec in records:
            try:
                rec["photos"] = get_house_photos(client, rec["id"],
                                                 size=args.photo_size, language=args.language)
            except ApiError as exc:
                rec["photos"] = []
                rec["photosError"] = str(exc)

    if args.json:
        out = {
            "query": {
                "arrival": args.arrival, "departure": args.departure,
                "adults": args.adults, "children": args.children, "pets": args.pets,
                "locations": args.location or [], "facilities": args.facility or [],
                "flexible": args.flexible, "sort": args.sort,
            },
            "currency": currency,
            "totalMatches": meta["totalHouses"],
            "returned": len(records),
            "houses": records,
        }
        if args.include_alternatives:
            out["alternativeHouses"] = [simplify_house(h, currency) for h in alternatives]
            out["totalAlternatives"] = meta["totalAlternativeHouses"]
        json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    if not records:
        print("No houses found for this search.")
        if meta.get("totalAlternativeHouses"):
            print(f"({meta['totalAlternativeHouses']} alternative dates/houses exist; "
                  f"re-run with --json --include-alternatives to see them)")
        return
    stay = f" for {args.arrival} → {args.departure}" if args.arrival else ""
    print(f"{meta['totalHouses']} houses available{stay}, showing {len(records)} "
          f"(sorted by {args.sort}, prices in {currency}):\n")
    for i, rec in enumerate(records, 1):
        print_house_text(rec, i)


def cmd_details(args, client):
    data = get_house_details(client, args.house_id, language=args.language)
    if args.json:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return
    loc = data.get("location") or {}
    print(f"{data.get('name')} (id {data.get('id')}, {data.get('type')})")
    print(f"{data.get('address')}, {data.get('postalCode')} {data.get('city')}, "
          f"{loc.get('name')} ({data.get('country')})")
    print(house_url(data.get("id")))
    print(f"rating: {data.get('rating')}/5 ({data.get('ratingCount')} reviews)")
    for tr in data.get("translations") or []:
        if tr.get("language", "").lower() == args.language:
            if tr.get("title"):
                print(f"\n{tr['title']}")
            print(f"\n{tr.get('description', '').strip()}")
            break


def cmd_photos(args, client):
    urls = get_house_photos(client, args.house_id, size=args.size, language=args.language)
    if args.json:
        json.dump({"houseId": args.house_id, "size": args.size, "photos": urls},
                  sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        for url in urls:
            print(url)


def cmd_quote(args, client):
    data = get_quote(client, args.house_id, args.arrival, args.departure,
                     adults=args.adults, pets=args.pets, language=args.language)
    if args.json:
        json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return
    cur = data.get("currency", "DKK")
    print(f"house {data.get('houseId')}: {args.arrival} → {args.departure} "
          f"({data.get('duration')} nights)")
    print(f"rent: {data.get('price'):.2f} {cur}")
    print(f"mandatory products: {data.get('productsPrice'):.2f} {cur}")
    if data.get("discount"):
        print(f"discount: -{data.get('discount'):.2f} {cur}")
    print(f"TOTAL: {data.get('priceWithDiscount'):.2f} {cur}")
    mandatory = [p for p in data.get("products") or [] if p.get("minQuantity", 0) >= 1]
    if mandatory:
        print("included mandatory products:")
        for p in mandatory:
            print(f"  - {p.get('name')}: {p.get('price'):.2f} {cur}")


def cmd_availability(args, client):
    pairs = get_availabilities(client, args.house_id, args.date_from, args.date_to)
    if args.json:
        json.dump({"houseId": args.house_id, "availablePeriods": pairs},
                  sys.stdout, ensure_ascii=False, indent=2)
        print()
    else:
        if not pairs:
            print("No bookable periods found in the requested window.")
        for p in pairs:
            print(f"{p['arrival']} → {p['departure']}")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="danibo",
        description="Search holiday houses on danibo.dk (Fanø) for a date range. "
                    "All prices from 'search' are in EUR (German site version); "
                    "'quote' returns the exact booking price in DKK.",
    )
    # Global options are accepted both before and after the subcommand.
    def add_global_options(target, suppress=False):
        d = (lambda v: argparse.SUPPRESS if suppress else v)
        target.add_argument("--language", choices=["de", "da"], default=d("de"),
                            help="site language; de = EUR prices, da = DKK prices (default: de)")
        target.add_argument("--throttle", type=float, default=d(0.8),
                            help="minimum seconds between API requests (default: 0.8)")
        target.add_argument("--retries", type=int, default=d(4),
                            help="retries on transient errors (default: 4)")
        target.add_argument("--cache-ttl", type=int, default=d(900),
                            help="cache lifetime in seconds for search results, 0 disables (default: 900)")
        target.add_argument("--no-cache", action="store_true", default=d(False),
                            help="bypass the response cache")
        target.add_argument("--verbose", action="store_true", default=d(False),
                            help="log requests to stderr")

    add_global_options(parser)
    common = argparse.ArgumentParser(add_help=False)
    add_global_options(common, suppress=True)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", parents=[common],
                       help="search available houses for a date range")
    p.add_argument("--arrival", type=check_date, help="arrival date YYYY-MM-DD")
    p.add_argument("--departure", type=check_date, help="departure date YYYY-MM-DD")
    p.add_argument("--flexible", action="store_true",
                   help="allow flexible arrival dates around the requested range")
    p.add_argument("--adults", type=int, default=2, help="number of adults (default: 2)")
    p.add_argument("--children", type=int, default=0, help="number of children (default: 0)")
    p.add_argument("--pets", type=int, default=0, help="number of pets (default: 0)")
    p.add_argument("--location", action="append", choices=sorted(LOCATIONS),
                   help="restrict to area, repeatable (rindby, fanoe-bad, soenderho, nordby)")
    p.add_argument("--type", choices=sorted(HOUSE_TYPES),
                   help="accommodation type (house, hotel, camping, tent)")
    p.add_argument("--facility", action="append", choices=sorted(FACILITIES),
                   help="required facility, repeatable (extended search checkboxes)")
    p.add_argument("--bedrooms", type=int, default=1, help="minimum bedrooms (default: 1)")
    p.add_argument("--bathrooms", type=int, default=1, help="minimum bathrooms (default: 1)")
    p.add_argument("--max-price", type=int, default=0,
                   help="maximum price for the stay (0 = no limit)")
    p.add_argument("--min-sqm", type=int, default=0, help="minimum living area m² (0 = any)")
    p.add_argument("--min-build-year", type=int, default=0, help="minimum build year (0 = any)")
    p.add_argument("--max-distance-coast", type=int, default=0,
                   help="max distance to beach in meters (0 = any)")
    p.add_argument("--max-distance-store", type=int, default=0,
                   help="max distance to shopping in meters (0 = any)")
    p.add_argument("--keyword", help="catalogue number / street / area free-text search")
    p.add_argument("--sort", choices=["price", "rating", "size", "beach"], default="price",
                   help="sort order of results (default: price ascending)")
    p.add_argument("--cheapest", type=int, metavar="N",
                   help="shortcut: only output the N cheapest results")
    p.add_argument("--limit", type=int, help="maximum number of results to output")
    p.add_argument("--with-photos", action="store_true",
                   help="also fetch photo URLs for each returned house (one extra request per house)")
    p.add_argument("--photo-size", choices=["Small", "Medium", "Large"], default="Medium")
    p.add_argument("--include-alternatives", action="store_true",
                   help="with --json: include the site's alternative suggestions")
    p.add_argument("--page-size", type=int, default=50, help="API page size (default: 50)")
    p.add_argument("--max-pages", type=int, help="stop after N result pages")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("details", parents=[common], help="full details for one house")
    p.add_argument("house_id", type=int)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_details)

    p = sub.add_parser("photos", parents=[common], help="photo URLs for one house")
    p.add_argument("house_id", type=int)
    p.add_argument("--size", choices=["Small", "Medium", "Large"], default="Large")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_photos)

    p = sub.add_parser("quote", parents=[common], help="exact booking price (DKK) for a house and date range")
    p.add_argument("house_id", type=int)
    p.add_argument("--arrival", type=check_date, required=True)
    p.add_argument("--departure", type=check_date, required=True)
    p.add_argument("--adults", type=int, default=2)
    p.add_argument("--pets", type=int, default=0)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_quote)

    p = sub.add_parser("availability", parents=[common], help="bookable arrival/departure dates for a house")
    p.add_argument("house_id", type=int)
    p.add_argument("--from", dest="date_from", type=check_date, help="window start YYYY-MM-DD")
    p.add_argument("--to", dest="date_to", type=check_date, help="window end YYYY-MM-DD")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_availability)

    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    client = ApiClient(
        throttle=max(0.0, args.throttle),
        retries=max(0, args.retries),
        cache_ttl=args.cache_ttl,
        cache_enabled=not args.no_cache,
        verbose=args.verbose,
    )
    try:
        args.func(args, client)
    except ApiError as exc:
        sys.exit(f"error: {exc}")
    except BrokenPipeError:
        # output piped into e.g. `head` — exit quietly
        try:
            sys.stdout.close()
        except OSError:
            pass
        os._exit(0)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
