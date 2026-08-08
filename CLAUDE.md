# git-heatmap — Claude Code Instructions

## What this is

A single-file Python 3 CLI that turns `git log` into a GitHub-style commit calendar as one self-contained HTML file. Installed on `PATH` as `git-heatmap`, which makes git expose it as `git heatmap`.

See [README.md](README.md) for usage, options, and the two data-reading caveats (window-relative shading, author-date bucketing).

## Hard constraints

- **Standard library only.** No pip installs, no venv, no `requirements.txt`. The whole value proposition is that this runs anywhere Python 3 and git exist. If a change seems to need a dependency, it doesn't.
- **One file.** `git-heatmap` holds the CLI *and* the HTML template. Do not split the template into a separate file — the script must stay copyable to a new machine on its own.
- **Self-contained output.** The generated page must never reference an external URL, CDN, font, or stylesheet. `TestRender.test_is_self_contained` enforces this; keep it passing.
- **`str.replace`, never `.format`/f-strings, on the template.** It is dense with CSS and JS braces that format-string parsing would misread. Placeholders are `__DATA_JSON__`, `__META_JSON__`, `__TITLE__`.

## Testing

```bash
python3 -m unittest discover -s tests -v
```

TDD applies: write the failing test first. Fixture repos are built programmatically with `GIT_AUTHOR_DATE`/`GIT_COMMITTER_DATE` backdating and identity pinned via `-c user.name=...`, so tests never read global git config and no binary git data is committed.

**The Python tests cannot reach the rendering logic.** Bucketing, month labels, streak counting, and the window selector are JavaScript inside the template. Changes there require generating a page and looking at it. Headless Chromium works:

```bash
git heatmap -o /tmp/p.html --no-open
"/Applications/Chromium.app/Contents/MacOS/Chromium" --headless --disable-gpu \
  --screenshot=/tmp/p.png --window-size=1200,1000 --hide-scrollbars \
  --virtual-time-budget=4000 "file:///tmp/p.html"
```

### Cases that have actually broken

Check these two whenever you touch the calendar JS — both shipped broken once:

1. **A calendar-year window.** Its grid starts on the Sunday *before* Jan 1, so the leading column belongs mostly to the previous December. Labelling from the column's first day let December claim the slot and suppress "Jan" entirely. Labels must derive from each column's first **in-range** day.
2. **A repo dormant for over a year.** "Last 12 months" is anchored to today, so a dormant repo opens on an empty grid. The page falls back to the most recent year that has commits. Build a fixture with backdated commits to exercise it — every local repo is active, so normal use never hits this path.

### Dark mode

Both themes are *selected*, not flipped: each has its own green ramp stepped for its own surface. Declare dark values under both `@media (prefers-color-scheme: dark)` and `:root[data-theme="dark"]` so an explicit toggle beats the OS setting in both directions.

Controls carry `appearance: none`. Without it, a `var()` that fails to resolve drops the whole declaration and the browser repaints the control as an unreadable native system-gray pill — which is exactly what happened before the fix.

## Colour

The five-step ramp is sequential: one hue, light→dark, monotone lightness, with a visible step between the empty cell and level 1 (that gap is what makes "no commits" distinguishable from "one commit" — the thing GitHub's own graph is weakest on). If you restep it, keep those three properties. Do not introduce a second hue; a rainbow ramp on a magnitude scale is wrong regardless of how it looks.

## Conventions

- `set up` (verb) vs `setup` (noun) — method names use `setUpFoo`.
- Document public functions with docstrings; keep comments to the non-obvious *why*.
- One blank line at end of file.
- Exit codes are load-bearing: 0 ok, 1 error, 2 no matching commits. Don't collapse 2 into 1.
