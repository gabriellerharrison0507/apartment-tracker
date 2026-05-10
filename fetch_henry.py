import json
import os
import urllib.request
from datetime import datetime
from playwright.sync_api import sync_playwright

SNAPSHOTS_FILE = "data/henry-snapshots.json"
CONFIG_FILE = "gist_config.json"
URL = "https://www.thehenrydenver.com/Floor-plans.aspx"
GIST_FILENAME = "henry-snapshots.json"

# Plans excluded — no balcony
EXCLUDED_PLANS = {"A3", "A5"}


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
        print(f"Pushed {len(snapshots)} Henry snapshots to Gist {gist_id[:8]}…")
        return gist_id
    else:
        result = gist_request("POST", "/gists", token, {
            "description": "RoomList — Henry unit snapshots",
            "public": False,
            "files": files,
        })
        new_id = result["id"]
        print(f"Created new Gist {new_id[:8]}… with {len(snapshots)} Henry snapshots")
        return new_id


def fetch_henry_units():
    """
    The Henry uses api.ws.realpage.com:
    - GET /v2/property/8715460/floorplans  -> response.floorplans[{id, name}]
    - GET /v2/property/8715460/units?...   -> response.units[{unitNumber, floorplanId, numberOfBeds, floorNumber, squareFeet, rent, internalAvailableDate}]
    """
    fp_data = {}   # floorplanId -> plan name
    units_data = []

    def on_response(response):
        url = response.url
        if "api.ws.realpage.com" not in url:
            return
        try:
            body = response.json()
            resp = body.get("response", {})
            if "floorplans" in url:
                for fp in resp.get("floorplans", []):
                    fp_data[fp["id"]] = fp.get("name", "")
            elif "/units" in url:
                units_data.extend(resp.get("units", []))
        except Exception:
            pass

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
        page.on("response", on_response)
        page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(8000)
        browser.close()

    print(f"Floorplans captured: {len(fp_data)} | Units captured: {len(units_data)}")

    if not units_data:
        raise ValueError("No units data captured from api.ws.realpage.com/units endpoint")

    # Filter to 1BR, exclude plans with no balcony
    one_bed = [
        u for u in units_data
        if u.get("numberOfBeds") == 1
        and fp_data.get(u.get("floorplanId"), "") not in EXCLUDED_PLANS
    ]

    if not one_bed:
        raise ValueError(f"No eligible 1BR units. Total captured: {len(units_data)}")

    today = datetime.now().strftime("%-m/%-d/%Y")
    snapshot = {"date": today, "units": {}}

    for u in one_bed:
        code = str(u.get("unitNumber", ""))
        if not code:
            continue
        plan = fp_data.get(u.get("floorplanId"), "")
        sqft = int(u.get("squareFeet") or 0)
        avail_raw = u.get("internalAvailableDate", "") or ""
        avail = avail_raw[:10] if avail_raw else ""  # "2026-06-01 00:00 -0600" -> "2026-06-01"
        rent = int(u.get("rent") or 0)
        snapshot["units"][code] = {
            "plan": plan,
            "sqft": sqft,
            "availDate": avail,
            "minRent": rent,
        }

    return snapshot


def main():
    os.makedirs("data", exist_ok=True)
    cfg = load_config()
    token = os.environ.get("GIST_TOKEN") or cfg.get("gist_token", "")
    if os.environ.get("GIST_ID"):
        cfg["gist_id"] = os.environ.get("GIST_ID")

    snapshots = []
    if os.path.exists(SNAPSHOTS_FILE):
        with open(SNAPSHOTS_FILE) as f:
            snapshots = json.load(f)

    try:
        snapshot = fetch_henry_units()
    except Exception as e:
        print(f"WARNING: Failed to fetch Henry units: {e}. Skipping today.")
        return

    existing = next((i for i, s in enumerate(snapshots) if s["date"] == snapshot["date"]), None)
    if existing is not None:
        snapshots[existing] = snapshot
        print(f"Updated Henry snapshot for {snapshot['date']} ({len(snapshot['units'])} units)")
    else:
        snapshots.append(snapshot)
        print(f"Added Henry snapshot for {snapshot['date']} ({len(snapshot['units'])} units)")

    with open(SNAPSHOTS_FILE, "w") as f:
        json.dump(snapshots, f, indent=2)

    print(f"Total Henry snapshots: {len(snapshots)}")

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
        print("No gist_token — skipping cloud sync")


if __name__ == "__main__":
    main()
