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


def find_unit_array(data):
    """Recursively search for an array that looks like unit/floorplan data."""
    unit_keys = {"UnitCode", "unitCode", "FloorplanName", "floorplanName",
                 "Beds", "beds", "NumBedrooms", "MinRent", "minRent", "UnitNumber"}

    def looks_like_units(val):
        if not isinstance(val, list) or not val:
            return False
        sample = val[0]
        return isinstance(sample, dict) and bool(unit_keys & set(sample.keys()))

    if looks_like_units(data):
        return data

    if isinstance(data, dict):
        for v in data.values():
            if looks_like_units(v):
                return v
            if isinstance(v, dict):
                for v2 in v.values():
                    if looks_like_units(v2):
                        return v2
            if isinstance(v, list):
                for item in v:
                    result = find_unit_array(item)
                    if result:
                        return result

    return None


def get_field(obj, *keys):
    """Return first non-None value from a list of candidate key names."""
    for k in keys:
        if obj.get(k) is not None:
            return obj[k]
    return None


def extract_floor(code):
    """Extract floor number from unit code (e.g. '501' -> 5, '0501' -> 5)."""
    stripped = str(code).lstrip("0") or "0"
    return int(stripped[0]) if stripped else 0


def fetch_henry_units():
    captured = []

    def on_response(response):
        url = response.url
        if "realpage.com" not in url and "leasestar" not in url:
            return
        try:
            data = response.json()
            captured.append({"url": url, "data": data})
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
        page.goto(URL, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(5000)
        browser.close()

    print(f"Captured {len(captured)} RealPage API responses:")
    for r in captured:
        print(f"  {r['url'][:100]}")

    all_units = None
    for resp in captured:
        all_units = find_unit_array(resp["data"])
        if all_units:
            print(f"Found unit data ({len(all_units)} items) at: {resp['url'][:80]}")
            break

    if not all_units:
        raise ValueError(
            f"Could not find unit array in {len(captured)} API responses. "
            f"URLs: {[r['url'][:80] for r in captured]}"
        )

    # Filter to 1BR, exclude plans with no balcony
    one_bed = []
    for u in all_units:
        beds = get_field(u, "Beds", "beds", "NumBedrooms", "numBedrooms") or 0
        plan = str(get_field(u, "FloorplanName", "floorplanName", "PlanName") or "")
        if int(beds) == 1 and plan not in EXCLUDED_PLANS:
            one_bed.append(u)

    if not one_bed:
        raise ValueError(f"No eligible 1BR units found. Total scraped: {len(all_units)}")

    today = datetime.now().strftime("%-m/%-d/%Y")
    snapshot = {"date": today, "units": {}}

    for u in one_bed:
        code = str(get_field(u, "UnitCode", "unitCode", "UnitNumber", "unitNumber") or "")
        if not code:
            continue
        plan = str(get_field(u, "FloorplanName", "floorplanName", "PlanName") or "")
        sqft = int(get_field(u, "SqFt", "sqft", "SquareFeet", "squareFeet") or 0)
        avail_raw = str(get_field(u, "AvailableDate", "availableDate", "MoveInDate") or "")
        avail = avail_raw.split("T")[0] if avail_raw else ""
        rent = int(get_field(u, "MinRent", "minRent", "Rent", "rent") or 0)
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
