# danibo-cli

Command-line tool to search holiday houses and apartments on
[danibo.dk](https://www.danibo.dk/de/) (island of Fanø, Denmark) for a
defined date range — with prices, availability, full details and photos.

It talks to the same public JSON API that powers the website's own search
and extended search ("Erweiterte Suche"). No HTML scraping, no login, no
API key.

- **No dependencies** — a single file, Python 3.8+ standard library only.
- **Robust** — request throttling with jitter, exponential-backoff retries
  on 429/5xx/network errors (honours `Retry-After`), and an on-disk response
  cache, so repeated queries don't hammer the site or trip rate limits.
- **AI-friendly** — `--json` emits stable, structured output; `--cheapest N`
  answers "what are the cheapest options for these dates" in one call.

## Usage

```sh
./danibo.py search --arrival 2026-09-05 --departure 2026-09-12 --adults 2
```

### Find the cheapest options (human-readable)

```sh
./danibo.py search --arrival 2026-09-05 --departure 2026-09-12 --cheapest 5
```

### Machine-readable output for AI agents

```sh
./danibo.py search --arrival 2026-09-05 --departure 2026-09-12 \
    --adults 2 --children 1 --pets 1 --cheapest 5 --json
```

Returns a JSON document with `totalMatches`, the query echo, and per house:
id, name, type, address, location, detail-page URL, coordinates, rating,
capacity (persons/pets/bedrooms/bathrooms/m²), distance to beach and
shopping, facility list, the confirmed available date range, nights, and
the price breakdown (`rentPrice`, `mandatoryProductsPrice`, `discount`,
`totalPrice`, `currency`). Everything `/api/search` returns is available —
add `--with-photos` to include photo URLs per house.

### Extended-search filters

All filters of the website's "Erweiterte Suche" are supported:

```sh
./danibo.py search --arrival 2026-10-17 --departure 2026-10-24 \
    --adults 4 --pets 1 \
    --location rindby --location soenderho \
    --facility sauna --facility whirlpool --facility internet \
    --max-price 1500 --min-sqm 80 --min-build-year 2000 \
    --max-distance-coast 1000 --max-distance-store 2000 \
    --bedrooms 3 --bathrooms 1 --sort price
```

- `--location`: `rindby`, `fanoe-bad`, `soenderho`, `nordby` (repeatable)
- `--type`: `house`, `hotel`, `camping`, `tent`
- `--facility` (repeatable): `washer`, `dishwasher`, `pool`, `whirlpool`,
  `sauna`, `seaview`, `stove`, `internet`, `nonsmoking`, `ev-charger`,
  `heatpump`, `activityroom`, `extra-toilet`, `luxury`
- `--flexible`: allow flexible arrival around the requested dates
- `--keyword`: catalogue number / street / area free-text
- `--sort`: `price` (default), `rating`, `size`, `beach`

### Other commands

```sh
./danibo.py details 3435                 # full description of a house
./danibo.py photos 3435 --size Large     # photo URLs (Small/Medium/Large)
./danibo.py availability 3435 --from 2026-09-01 --to 2026-10-31
./danibo.py quote 3435 --arrival 2026-09-05 --departure 2026-09-12 --adults 2
```

Every command accepts `--json`.

## Prices, currency, availability

- `search` returns prices as shown on the German site version (**EUR**,
  `--language da` switches to DKK). `totalPrice` includes mandatory
  extras (cleaning, booking fee) and discounts — the same number the
  website shows.
- `quote` calls the booking-price endpoint and returns the exact bookable
  total in **DKK**, itemising the mandatory products.
- The search endpoint only returns periods that are actually bookable, so
  every result is available for the shown arrival→departure range. Houses
  with slightly different available dates appear as *alternatives*
  (`--json --include-alternatives`).

## Rate-limit friendliness

Requests are serialized with a minimum gap (`--throttle`, default 0.8 s
plus jitter). Transient errors are retried up to `--retries` times (default
4) with exponential backoff. Responses are cached in
`~/.cache/danibo-cli/` — searches for 15 minutes (`--cache-ttl`), house
details and photos for 24 hours, quotes/availability for 5 minutes. Use
`--no-cache` to force fresh data and `--verbose` to log every request.

## Example: AI workflow "check for cheapest prices"

```sh
# 1. cheapest 3 houses for the week, structured:
./danibo.py search --arrival 2026-09-05 --departure 2026-09-12 --cheapest 3 --json

# 2. verify the exact booking total for the winner:
./danibo.py quote <houseId> --arrival 2026-09-05 --departure 2026-09-12 --json
```
