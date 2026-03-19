import json
import re
import os
import urllib.request
from datetime import datetime
from playwright.sync_api import sync_playwright

SNAPSHOTS_FILE = "data/snapshots.json"
CONFIG_FILE = "gist_config.json"
URL = "https://www.lyraapartments.com/floorplans"
GIST_FILENAME = "lyra-snapshots.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def gist_request(method, path, token, body=None):
    url = "https://api.github.com" + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

def push_to_gist(snapshots, token, gist_id=None):
    content = json.dumps(snapshots, indent=2)
    files = {GIST_FILENAME: {"content": content}}

    if gist_id:
        gist_request("PATCH", f"/gists/{gist_id}", token, {"files": files})
        print(f"Pushed {len(snapshots)} snapshots to Gist {gist_id[:8]}…")
        return gist_id
    else:
        result = gist_request("POST", "/gists", token, {
            "description": "RoomList — Lyra unit snapshots",
            "public": False,
            "files": files,
        })
        new_id = result["id"]
        print(f"Created new Gist {new_id[:8]}… and pushed {len(snapshots)} snapshots")
        return new_id

def fetch_units():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        page.goto(URL, wait_until="load", timeout=90000)
        page.wait_for_timeout(3000)
        html = page.content()
        browser.close()

    idx = html.find('"UnitCode"')
    if idx == -1:
        raise ValueError("Could not find UnitCode in page HTML")

    start = html.rfind('[', 0, idx)
    if start == -1:
        raise ValueError("Could not find array start before UnitCode")
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

    today = datetime.now().strftime("%-m/%-d/%Y")
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
    cfg = load_config()
    token = cfg.get("gist_token", "")

    snapshots = []
    if os.path.exists(SNAPSHOTS_FILE):
        with open(SNAPSHOTS_FILE) as f:
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

    if token:
        try:
            gist_id = cfg.get("gist_id", "")
            new_id = push_to_gist(snapshots, token, gist_id or None)
            if new_id != gist_id:
                cfg["gist_id"] = new_id
                save_config(cfg)
        except Exception as e:
            print(f"WARNING: Gist push failed: {e}")
    else:
        print("No gist_token in gist_config.json — skipping cloud sync")

if __name__ == "__main__":
    main()
