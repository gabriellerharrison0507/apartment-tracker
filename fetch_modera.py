import json
import os
import time
import urllib.request
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth

SNAPSHOTS_FILE = "data/modera-snapshots.json"
CONFIG_FILE = "gist_config.json"
URL = "https://www.moderawestwashpark.com/denver/modera-west-wash-park/conventional/"
GIST_FILENAME = "modera-snapshots.json"


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
        print(f"Pushed {len(snapshots)} Modera snapshots to Gist {gist_id[:8]}…")
        return gist_id
    else:
        result = gist_request("POST", "/gists", token, {
            "description": "RoomList — Modera unit snapshots",
            "public": False,
            "files": files,
        })
        new_id = result["id"]
        print(f"Created new Gist {new_id[:8]}… with {len(snapshots)} Modera snapshots")
        return new_id


def fetch_modera_units():
    """
    Loads the Modera floor plans page via Playwright, waits for Cloudflare to
    resolve, then reads the embedded unitsDataDetails JS variable.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-US",
        )
        page = context.new_page()
        Stealth().apply_stealth_sync(page)
        page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        # Wait for Cloudflare challenge to resolve and unitsData to be populated
        page.wait_for_function("typeof unitsData !== 'undefined'", timeout=40000)
        page.wait_for_timeout(2000)

        two_bed = page.evaluate("""() => {
            const details = JSON.parse(unitsDataDetails);
            const result = [];
            for (const [fp_id, units] of Object.entries(details)) {
                for (const u of units) {
                    if (u.bedroom === 2 && u.bathroom === 2) {
                        result.push({
                            unit_number: u.unit_number,
                            floorplan_name: u.floorplan_name,
                            sqft: u.sqft || u.sqft_unit,
                            available_on: u.available_on,
                            min_rent: u.min_rent,
                        });
                    }
                }
            }
            return result;
        }""")
        browser.close()

    if not two_bed:
        raise ValueError("No 2BR/2BA units found in unitsDataDetails")

    today = datetime.now().strftime("%-m/%-d/%Y")
    snapshot = {"date": today, "units": {}}

    for u in two_bed:
        code = str(u["unit_number"])
        plan = u["floorplan_name"] or ""
        sqft = int(u["sqft"]) if u["sqft"] else 0
        avail_raw = u.get("available_on") or ""
        # Convert "MM/DD/YYYY" → "YYYY-MM-DD"
        try:
            avail = datetime.strptime(avail_raw, "%m/%d/%Y").strftime("%Y-%m-%d") if avail_raw else ""
        except ValueError:
            avail = ""
        rent = int(float(u["min_rent"])) if u["min_rent"] else 0
        floor = int(code) // 100

        snapshot["units"][code] = {
            "plan": plan,
            "sqft": sqft,
            "availDate": avail,
            "minRent": rent,
            "floor": floor,
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

    snapshot = None
    for attempt in range(1, 4):
        try:
            snapshot = fetch_modera_units()
            break
        except Exception as e:
            print(f"Attempt {attempt}/3 failed: {e}")
            if attempt < 3:
                print("Retrying in 15s…")
                time.sleep(15)
    if snapshot is None:
        print("WARNING: All 3 attempts failed. Skipping today.")
        return

    existing = next((i for i, s in enumerate(snapshots) if s["date"] == snapshot["date"]), None)
    if existing is not None:
        snapshots[existing] = snapshot
        print(f"Updated Modera snapshot for {snapshot['date']} ({len(snapshot['units'])} units)")
    else:
        snapshots.append(snapshot)
        print(f"Added Modera snapshot for {snapshot['date']} ({len(snapshot['units'])} units)")

    with open(SNAPSHOTS_FILE, "w") as f:
        json.dump(snapshots, f, indent=2)

    print(f"Total Modera snapshots: {len(snapshots)}")

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
