---
description: Full context for editing Gabby's apartment tracker site. Load this before making any changes.
---

# Apartment Tracker — Project Context

Gabby's personal move-to-Denver tracker. Deployed at GitHub Pages from the `main` branch.

## Key Facts
- **Target move-out**: July 1, 2026 (first week off work)
- **Target apartment**: Lyra Apartments, Denver — 1BR
- **Dream unit**: A7 floor 6 | Top picks: A7 any floor, A4 floor 5–6
- **Gabby's income**: $1,611.55/week → $6,980/mo

## File Structure

```
apartment-tracker/
├── index.html           # Entire app — all CSS, JS, HTML in one file
├── fetch_units.py       # Python/Playwright scraper for Lyra floor plan prices
├── gist_config.json     # GitHub token + Gist ID (git-ignored, do NOT commit)
├── data/snapshots.json  # Historical unit price data
└── .github/workflows/fetch-units.yml  # Daily GitHub Actions scrape at 8am MDT
```

**There is no build step.** Open index.html directly in a browser.

## Architecture

Single-page vanilla JS app, no frameworks. Three tabs:

### Tab 1: List (Furnishing Tracker)
- 6 rooms: Kitchen, Bathroom, Bedroom, Living Room, Balcony, Cleaning
- Per-item: cost range, actual price, URL, notes, purchased/owned status
- Persisted in `localStorage` key `aptTracker_data`

### Tab 2: Units (Lyra Apartment Tracker)
- Shows daily snapshots of 1BR availability + pricing at Lyra
- Dashboard cards, sortable table, price change tracking, watch list
- Charts: inventory trend (bar) + price trend by unit/plan (line) via Chart.js CDN
- Unit preference badges: Dream (A7 floor 6), Top Pick (A7 any / A4 high floor), Great, Island, High Floor
- "Ideal Date" badge for units available June 1+

### Tab 3: Savings (Financial Planning)
- Overview, Plan (month-by-month chart), Budget (post-move) sub-tabs
- Calculates projected move-out date dynamically from savings rate vs goal
- Adjustable sliders: rent payment to mom ($0–$800), future rent choice ($1,800–$2,000)

## Key JS Constants (in index.html)

```js
// Income
SAV_WEEKLY = 1611.55
SAV_MONTHLY_INCOME = 6980.42  // weekly × 52 ÷ 12

// Expenses while at mom's
SAV_MOM_EXPENSES = { carInsurance:40, studentLoans:50, subscriptions:30,
                     gym:100, gas:120, eatingOut:300, misc:110 }

// Move-in costs (July 1, full month)
SAV_MOVE_IN_COSTS = { firstMonth: 1900, securityDeposit: 500 }  // total $2,400

// Goal
SAV_FURNISHING_TOTAL = 4808   // midpoint of furnishing list
// Emergency fund = 6 × essentials (rent, groceries, insurance, student loans, gas)

// Gist
GIST_FILENAME = "lyra-snapshots.json"
GIST_ID_DEFAULT = "54001e64dfc9c3fb5bed99e13e23004a"
GIST_OWNER = "gabriellerharrison0507"
```

## Data Flow: Unit Snapshots

1. **fetch_units.py** runs daily at 8am MDT via GitHub Actions (or manually)
2. Scrapes `lyraapartments.com/floorplans` using Playwright/Chromium
3. Appends to `data/snapshots.json` and pushes to GitHub Gist
4. Site fetches from **raw Gist URL** (not GitHub API — avoids caching):
   `https://gist.githubusercontent.com/{owner}/{gist_id}/raw/{filename}?t={Date.now()}`
5. Snapshot structure: `[{ date: "M/D/YYYY", units: { code: { plan, sqft, availDate, minRent } } }]`

## localStorage Keys

| Key | Contents |
|-----|----------|
| `aptTracker_data` | All room items + purchased state |
| `aptTracker_nextId` | Next item ID counter |
| `aptTracker_unitSnapshots` | Cached unit snapshots (cleared by ↻ Refresh button) |
| `aptTracker_watched` | Watch list `{code: priceWhenWatched}` |

## Deployment

```bash
git add index.html
git commit -m "message"
git push   # GitHub Pages auto-deploys from main
```

Changes go live within ~1 minute of push.

## Common Issues & Fixes

- **Unit Tracker shows stale date**: Hit the ↻ Refresh button next to "Last snapshot" — clears localStorage cache and re-fetches raw Gist
- **Raw Gist URL**: Always use raw URL with `?t=Date.now()` and `cache: "no-store"` — the GitHub API endpoint has caching issues
- **Nested template literals**: The plan tab was rewritten using string concatenation (`+`) instead of nested backtick templates to avoid browser parsing bugs
- **Bar chart heights**: Use pixel heights (`120px` wrapper, JS calculates `hPx`) not percentages — flex children ignore `%` heights unreliably

## Design System

```css
--cream: #F0FAFA      /* background */
--ink: #0A2525        /* text */
--accent: #0ABAB5     /* teal, primary */
--pink: #FF0090       /* secondary */
--serif: 'DM Serif Display'
--sans: 'DM Sans'
```

## What NOT to Touch

- `gist_config.json` — never commit this (it has the GitHub token)
- The raw Gist fetch URL pattern — switching back to GitHub API breaks caching
