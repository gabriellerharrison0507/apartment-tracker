# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Gabby's personal move-to-Denver tracker. Single-page vanilla JS/CSS/HTML app — **no build step, no npm, no frameworks**. Open `index.html` directly in a browser. Deployed at `gabriellerharrison0507.github.io/apartment-tracker/` via GitHub Pages (auto-deploys on push to `main`).

- **Target move-out**: July 1, 2026
- **Target apartment**: Lyra Apartments, Denver — 1BR
- **Gabby's income**: $1,611.55/week → $6,980/mo

## File Structure

```
index.html                          # Entire app — all CSS, JS, HTML in one ~2000-line file
fetch_units.py                      # Python/Playwright daily scraper for Lyra floor plan prices
data/snapshots.json                 # Historical unit price snapshots (auto-updated by CI)
.github/workflows/fetch-units.yml   # Daily GitHub Actions scrape at 8am MDT
gist_config.json                    # GitHub token + Gist ID (git-ignored, never commit)
```

## Development

No build tools. Edit `index.html` directly, open in browser to test, then:

```bash
git add index.html
git commit -m "message"
git push   # live within ~1 minute
```

To run the scraper manually:
```bash
pip install playwright
playwright install chromium
GIST_TOKEN=<token> GIST_ID=<id> python fetch_units.py
```

## Architecture — Three Tabs in `index.html`

### Tab 1: List (Furnishing Tracker)
- 6 rooms: Kitchen, Bathroom, Bedroom, Living Room, Balcony, Cleaning
- Per-item: cost range, actual price, URL, notes, purchased/owned status, multiple product options
- Persisted in `localStorage` key `aptTracker_data`

### Tab 2: Units (Lyra Apartment Tracker)
- Daily snapshots of 1BR availability + pricing at Lyra
- Dashboard cards, sortable/filterable table, price change tracking, watch list
- Charts via Chart.js CDN: inventory trend (bar) + price trend by unit/plan (line)
- Unit preference badges: Dream (A7 floor 6), Top Pick (A7 any / A4 floor 5–6), Great, Island, High Floor
- "Ideal Date" badge for units available June 1+

### Tab 3: Savings (Financial Planning)
- Sub-tabs: Overview, Plan (month-by-month chart), Budget (post-move)
- Adjustable sliders: rent to mom ($0–$800), future rent ($1,800–$2,000)
- Dynamically recalculates projected move-out date and savings milestones

## Key JS Constants

```js
SAV_WEEKLY = 1611.55
SAV_MONTHLY_INCOME = 6980.42       // weekly × 52 ÷ 12
SAV_FURNISHING_TOTAL = 4808        // midpoint of furnishing list
SAV_MOVE_IN_COSTS = { firstMonth: 1900, securityDeposit: 500 }  // $2,400 total
GIST_FILENAME = "lyra-snapshots.json"
GIST_ID_DEFAULT = "54001e64dfc9c3fb5bed99e13e23004a"
GIST_OWNER = "gabriellerharrison0507"
```

## Data Flow: Unit Snapshots

1. `fetch_units.py` runs daily at 8am MDT via GitHub Actions
2. Scrapes `lyraapartments.com/floorplans` using Playwright/Chromium
3. Appends to `data/snapshots.json` and pushes to GitHub Gist
4. Site fetches from **raw Gist URL** with `?t=Date.now()` and `cache: "no-store"` (never the GitHub API — it has caching issues)
5. Snapshot structure: `[{ date: "M/D/YYYY", units: { code: { plan, sqft, availDate, minRent } } }]`

## localStorage Keys

| Key | Contents |
|-----|----------|
| `aptTracker_data` | All room items + purchased state |
| `aptTracker_nextId` | Next item ID counter |
| `aptTracker_unitSnapshots` | Cached unit snapshots (cleared by ↻ Refresh button) |
| `aptTracker_watched` | Watch list `{code: priceWhenWatched}` |

## Known Gotchas

- **Nested template literals**: The plan tab uses string concatenation (`+`) instead of nested backticks — avoid nested template literals to prevent browser parsing bugs
- **Bar chart heights**: Use pixel heights (`120px` wrapper, JS calculates `hPx`) not percentages — flex children ignore `%` heights unreliably
- **Raw Gist URL**: Always use the raw URL pattern, never the GitHub API endpoint

## Design System

```css
--cream: #F0FAFA      /* background */
--ink: #0A2525        /* text */
--accent: #0ABAB5     /* teal, primary */
--pink: #FF0090       /* secondary */
--serif: 'DM Serif Display'
--sans: 'DM Sans'
```
