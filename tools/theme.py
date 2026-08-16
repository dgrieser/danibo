"""The light/dark switch, shared by the reports and the Pages index.

Both stylesheets already carry a full dark palette behind
`prefers-color-scheme` and an explicit `[data-theme]` override. What is
missing is a way for the reader to pick: this module supplies the button,
its styles, the inline script that applies a stored choice before the first
paint, and the handler that flips it.

No stored choice means "follow the system" — the switch only ever writes
after a click.
"""

# Runs in <head> position, before anything is painted, so a stored choice
# never shows up as a flash of the other palette.
INIT = ("<script>try{var t=localStorage.getItem('danibo-theme');"
        "if(t==='light'||t==='dark')"
        "document.documentElement.setAttribute('data-theme',t)}catch(e){}</script>")

_SUN = ('<svg class="sun" viewBox="0 0 24 24" aria-hidden="true">'
        '<circle cx="12" cy="12" r="4.2"/>'
        '<path d="M12 2.2v2.4M12 19.4v2.4M4.4 4.4l1.7 1.7M17.9 17.9l1.7 1.7'
        'M2.2 12h2.4M19.4 12h2.4M4.4 19.6l1.7-1.7M17.9 6.1l1.7-1.7"/></svg>')
_MOON = ('<svg class="moon" viewBox="0 0 24 24" aria-hidden="true">'
         '<path d="M20.8 13.4A8.6 8.6 0 1 1 10.6 3.2a6.7 6.7 0 0 0 10.2 10.2Z"/></svg>')


def button(extra_class=""):
    """The switch. Shows the mode it would switch *to*, so the label reads as
    the action: 'Dunkel' while light, 'Hell' while dark."""
    cls = ("theme " + extra_class).strip()
    return (f'<button type="button" class="{cls}" '
            f'title="Zwischen hellem und dunklem Farbschema wechseln" '
            f'aria-label="Farbschema umschalten">'
            f'<span class="opt to-dark">{_MOON}<span>Dunkel</span></span>'
            f'<span class="opt to-light">{_SUN}<span>Hell</span></span>'
            f'</button>')


CSS = """
.topline{display:flex; align-items:center; justify-content:space-between;
  gap:16px; margin-bottom:16px}
.topline .eyebrow{margin-bottom:0}
.theme{font-family:var(--mono); font-size:11px; letter-spacing:.1em;
  text-transform:uppercase; color:var(--ink-2); background:var(--surface);
  border:1px solid var(--line); padding:6px 12px; border-radius:100px;
  cursor:pointer; line-height:1; flex:none;
  transition:border-color .15s,color .15s}
.theme:hover{border-color:var(--accent); color:var(--accent)}
.theme.in-controls{padding:7px 12px}
.theme .opt{display:none; align-items:center; gap:7px}
.theme svg{width:14px; height:14px; flex:none; fill:none; stroke:currentColor;
  stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round}
.theme .to-dark{display:inline-flex}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]) .theme .to-dark{display:none}
  :root:not([data-theme="light"]) .theme .to-light{display:inline-flex}
}
:root[data-theme="dark"] .theme .to-dark{display:none}
:root[data-theme="dark"] .theme .to-light{display:inline-flex}
@media (max-width:460px){.theme .opt span{display:none} .theme{padding:6px 9px}}
"""


JS = """
(function () {
  var root = document.documentElement, KEY = 'danibo-theme';
  function resolved() {
    var set = root.getAttribute('data-theme');
    if (set === 'light' || set === 'dark') return set;
    return window.matchMedia &&
      window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  Array.prototype.forEach.call(document.querySelectorAll('.theme'), function (btn) {
    btn.addEventListener('click', function () {
      var next = resolved() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem(KEY, next); } catch (e) {}
    });
  });
})();
"""
