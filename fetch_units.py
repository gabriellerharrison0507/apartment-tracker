import json
import re
import os
from datetime import datetime
from playwright.sync_api import sync_playwright

SNAPSHOTS_FILE = "data/snapshots.json"
URL = "https://www.lyraapartments.com/floorplans"

def fetch_units():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60000)
        html = page.content()
        browser.close()

    # Find the JSON units array embedded in the page
    match = re.search(r'\[\s*\{\s*"Id"\s*:', html)
    if not match:
        raise ValueError("Could not find units data in page HTML")

    start = match.start()
    depth = 0
    end = start
    for i, c in enumerate(html[start:]):
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                end = start + i + 1
                break

    units = json.loads(html[start:end])
    one_bed = [u for u in units if u.get("Beds") == 1]
    if not one_bed:
        raise ValueError("No 1-bedroom units found in data")

    today = datetime.utcnow().strftime("%-m/%-d/%Y")
    snapshot = {"date": today, "units": {}}

    for u in one_bed:
        code = str(u["UnitCode"])
        avail = u.get("AvailableDate", "").split("T")[0] if u.get("AvailableDate") else ""
        snapshot["units"][code] = {
            "plan": u.get("FloorplanName", ""),
            "sqft": u.get("SqFt", 0),
            "availDate": avail,
            "minRent": u.get("MinRent", 0),
        }

    return snapshot

def main():
    os.makedirs("data", exist_ok=True)

    snapshots = []
    if os.path.exists(SNAPSHOTS_FILE):
        with open(SNAPSHOTS_FILE, "r") as f:
            snapshots = json.load(f)

    try:
        snapshot = fetch_units()
    except Exception as e:
        print(f"WARNING: Failed to fetch units: {e}. Skipping today.")
        return

    existing = next((i for i, s in enumerate(snapshots) if s["date"] == snapshot["date"]), None)
    if existing is not None:
        snapshots[existing] = snapshot
        print(f"Updated snapshot for {snapshot['date']} ({len(snapshot['units'])} units)")
    else:
        snapshots.append(snapshot)
        print(f"Added snapshot for {snapshot['date']} ({len(snapshot['units'])} units)")

    with open(SNAPSHOTS_FILE, "w") as f:
        json.dump(snapshots, f, indent=2)

    print(f"Total snapshots: {len(snapshots)}")

if __name__ == "__main__":
    main()
