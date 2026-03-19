import requests
import json
import re
import os
from datetime import datetime

SNAPSHOTS_FILE = "data/snapshots.json"
URL = "https://www.lyraapartments.com/floorplans"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}

def fetch_units():
    response = requests.get(URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    html = response.text

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

    snapshot = fetch_units()

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
