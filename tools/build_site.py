#!/usr/bin/env python3
"""Build the GitHub Pages site from results/.

The reports in results/ are written for a host that wraps them in a document
skeleton, so they carry a <title> and a <style> but no doctype, charset or
viewport. Served straight from Pages that costs them the mobile viewport and
leaves the encoding to the server, so wrap each one into a complete document
here and generate an index over them.

Usage: python3 tools/build_site.py [output-dir]   (default: _site)
"""
import html
import json
import re
import shutil
import sys
from pathlib import Path

import theme

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
ASSETS = ROOT / "results" / "assets"

TITLE_RE = re.compile(r"<title>(.*?)</title>", re.I | re.S)
DOCTYPE_RE = re.compile(r"^\s*(<!doctype|<html\b)", re.I)


def wrap(body, title):
    """Give a report the document head it was written without."""
    return (
        "<!doctype html>\n<html lang=\"de\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        f"<title>{html.escape(title)}</title>\n"
        "</head>\n<body>\n" + body + "\n</body>\n</html>\n"
    )


def build_reports(out):
    """Copy each report into the site, wrapped, and return its manifest entry."""
    manifest = json.loads((RESULTS / "reports.json").read_text(encoding="utf-8"))
    known = {e["file"] for e in manifest}
    stray = sorted(p.name for p in RESULTS.glob("*.html") if p.name not in known)
    if stray:
        sys.exit(f"error: {', '.join(stray)} not listed in results/reports.json")

    entries = []
    for entry in manifest:
        src = RESULTS / entry["file"]
        if not src.exists():
            sys.exit(f"error: results/{entry['file']} listed in reports.json is missing")
        raw = src.read_text(encoding="utf-8")
        found = TITLE_RE.search(raw)
        title = entry.get("title") or (found.group(1).strip() if found else src.stem)
        page = raw if DOCTYPE_RE.match(raw) else wrap(raw, title)
        (out / entry["file"]).write_text(page, encoding="utf-8")

        data = entry.get("data")
        if data:
            data_src = RESULTS / data
            if not data_src.exists():
                sys.exit(f"error: results/{data} listed in reports.json is missing")
            (out / data).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(data_src, out / data)
            entry["dataSize"] = data_src.stat().st_size

        entry["title"] = title
        entry["size"] = src.stat().st_size
        entries.append(entry)
        print(f"  {entry['file']}  {entry['size']/1e6:.1f} MB"
              + (f"  + {data}" if data else ""))
    return entries


def human(size):
    if size >= 1e6:
        return f"{size/1e6:.1f}".replace(".", ",") + " MB"
    return f"{size/1e3:.0f} KB"


def copy_assets(out):
    """Reports and index share assets/ — photos and the display face — so the
    same relative paths resolve both in results/ and in the built site."""
    if not ASSETS.exists():
        return 0
    shutil.copytree(ASSETS, out / "assets")
    return sum(1 for p in (out / "assets").rglob("*") if p.is_file())


FONT_FACE = ("@font-face{font-family:'Fraunces';font-style:normal;font-weight:600;"
             "font-display:swap;src:url(assets/fraunces-600.woff2) format('woff2');}")


INDEX_CSS = """
*,*::before,*::after{box-sizing:border-box}
:root{
  color-scheme:light;
  --ground:#E7EAE6; --surface:#F8F9F6; --surface-2:#EFF2ED;
  --ink:#17201D; --ink-2:#586661; --ink-3:#7C8A85;
  --line:#CBD2CB; --line-soft:#DDE3DC;
  --accent:#1E5A5E; --accent-soft:#D6E3E2; --on-accent:#F8F9F6;
  --warm:#8F4526;
  --radius:3px;
  --display:'Fraunces','Iowan Old Style','Palatino Linotype',Palatino,Georgia,serif;
  --body:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
  --mono:ui-monospace,SFMono-Regular,'SF Mono','DejaVu Sans Mono',Menlo,Consolas,monospace;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    color-scheme:dark;
    --ground:#0E1513; --surface:#151E1B; --surface-2:#1B2622;
    --ink:#E4EAE5; --ink-2:#9CAAA4; --ink-3:#7B8983;
    --line:#2A3733; --line-soft:#222E2A;
    --accent:#7FBDBC; --accent-soft:#1B3A3A; --on-accent:#0E1513;
    --warm:#DE8B65;
  }
}
:root[data-theme="dark"]{
  color-scheme:dark;
  --ground:#0E1513; --surface:#151E1B; --surface-2:#1B2622;
  --ink:#E4EAE5; --ink-2:#9CAAA4; --ink-3:#7B8983;
  --line:#2A3733; --line-soft:#222E2A;
  --accent:#7FBDBC; --accent-soft:#1B3A3A; --on-accent:#0E1513;
  --warm:#DE8B65;
}
html{-webkit-text-size-adjust:100%}
body{margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--body); font-size:16px; line-height:1.55;
  min-height:100vh; display:flex; flex-direction:column}
.wrap{max-width:760px; margin:0 auto; padding:0 24px}
a{color:var(--accent); text-underline-offset:2px}
a:focus-visible{outline:2px solid var(--accent); outline-offset:3px; border-radius:2px}
header{border-bottom:1px solid var(--line); background:var(--surface)}
header .wrap{padding:52px 24px 36px}
.eyebrow{font-family:var(--mono); font-size:11px; letter-spacing:.16em;
  text-transform:uppercase; color:var(--ink-3); margin:0 0 16px}
h1{font-family:var(--display); font-weight:600; font-size:clamp(30px,6vw,46px);
  line-height:1.05; letter-spacing:-.015em; margin:0 0 12px; text-wrap:balance}
.dek{margin:0; color:var(--ink-2); font-size:17px; max-width:58ch}
main{flex:1 0 auto; padding:36px 0 8px}
.report{background:var(--surface); border:1px solid var(--line);
  border-radius:var(--radius); padding:24px 26px; margin-bottom:16px}
.report.highlight{border-color:var(--accent); box-shadow:inset 0 0 0 1px var(--accent)}
.report h2{font-family:var(--display); font-weight:600; font-size:24px;
  margin:0 0 4px; letter-spacing:-.01em}
.report h2 a{color:inherit; text-decoration:none}
.report h2 a:hover{color:var(--accent)}
.stay{font-family:var(--mono); font-size:12.5px; color:var(--ink-3);
  margin:0 0 12px; letter-spacing:.02em}
.report p.summary{margin:0 0 14px; color:var(--ink-2); font-size:15px; max-width:60ch}
ul.facts{list-style:none; padding:0; margin:0 0 18px; display:flex;
  flex-wrap:wrap; gap:6px}
ul.facts li{font-size:12.5px; padding:3px 10px; border-radius:100px;
  background:var(--accent-soft); color:var(--ink)}
.actions{display:flex; flex-wrap:wrap; gap:9px; align-items:center}
.btn{display:inline-block; font-size:14px; font-weight:600; text-decoration:none;
  padding:9px 17px; border-radius:100px; background:var(--accent);
  color:var(--on-accent); transition:filter .15s}
.btn:hover{filter:brightness(1.12)}
.btn.ghost{background:transparent; border:1px solid var(--line); color:var(--ink-2)}
.btn.ghost:hover{border-color:var(--accent); color:var(--accent)}
.size{font-family:var(--mono); font-size:11.5px; color:var(--ink-3)}
.empty{color:var(--ink-2); font-size:15px}
footer{border-top:1px solid var(--line); background:var(--surface); margin-top:30px}
footer .wrap{padding:26px 24px 42px}
footer p{margin:0 0 8px; font-size:14px; color:var(--ink-2); max-width:66ch}
footer code{font-family:var(--mono); font-size:12.5px; background:var(--surface-2);
  padding:1px 5px; border-radius:2px; border:1px solid var(--line-soft)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""


def build_index(out, entries, repo_url):
    cards = []
    for e in entries:
        facts = "".join(f"<li>{html.escape(f)}</li>" for f in e.get("facts", []))
        data = ""
        sizes = [f"HTML {human(e['size'])}"]
        if e.get("data"):
            data = f'<a class="btn ghost" href="{html.escape(e["data"])}">Rohdaten (JSON)</a>'
            sizes.append(f"JSON {human(e['dataSize'])}")
        stay = (f'<p class="stay">{html.escape(e["stay"])}</p>' if e.get("stay") else "")
        cards.append(f"""<article class="report{' highlight' if e.get("highlight") else ''}">
  <h2><a href="{html.escape(e['file'])}">{html.escape(e['title'])}</a></h2>
  {stay}
  <p class="summary">{html.escape(e.get('summary', ''))}</p>
  <ul class="facts">{facts}</ul>
  <div class="actions">
    <a class="btn" href="{html.escape(e['file'])}">Bericht öffnen</a>
    {data}
    <span class="size">{" · ".join(sizes)}</span>
  </div>
</article>""")

    body = "\n".join(cards) or '<p class="empty">Noch keine Berichte.</p>'
    page = f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>danibo · Rechercheergebnisse</title>
<style>{FONT_FACE}{INDEX_CSS}{theme.CSS}</style>
{theme.INIT}
</head>
<body>
<header>
  <div class="wrap">
    <div class="topline">
      <p class="eyebrow">danibo-cli</p>
      {theme.button()}
    </div>
    <h1>Rechercheergebnisse</h1>
    <p class="dek">Auswertungen konkreter Suchläufe auf danibo.dk (Insel Fanø),
    erhoben mit dem CLI-Tool in diesem Repository.</p>
  </div>
</header>
<main>
  <div class="wrap">
{body}
  </div>
</main>
<footer>
  <div class="wrap">
    <p>Preise und Verfügbarkeit sind Momentaufnahmen vom jeweiligen
    Erhebungsdatum — vor einer Buchung auf danibo.dk gegenprüfen.</p>
    <p>Quellcode und Reproduktionsbefehle im
    <a href="{html.escape(repo_url)}">Repository</a>. Berichte und Übersicht werden mit
    <code>tools/fetch_report_data.py</code> und <code>tools/build_report.py</code>
    erzeugt — ein weiterer Zeitraum ist ein zusätzliches
    <code>anreise:abreise</code>-Argument.</p>
  </div>
</footer>
<script>{theme.JS}</script>
</body>
</html>
"""
    (out / "index.html").write_text(page, encoding="utf-8")


def main():
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "_site")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    # Tell Pages not to run the files through Jekyll, which would drop any
    # future path starting with an underscore.
    (out / ".nojekyll").write_text("", encoding="utf-8")

    print(f"building into {out}")
    n = copy_assets(out)
    print(f"  assets/  {n} file(s)")
    entries = build_reports(out)
    build_index(out, entries, "https://github.com/dgrieser/danibo")
    print(f"  index.html  ({len(entries)} report(s))")


if __name__ == "__main__":
    main()
