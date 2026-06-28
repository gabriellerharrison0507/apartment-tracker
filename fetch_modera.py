import json
import os
import re
import time
import urllib.request
from datetime import datetime
from curl_cffi import requests as cf_requests

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
    Fetches the Modera floor plans page using curl_cffi (Chrome TLS fingerprint)
    to bypass Cloudflare, then parses the embedded unitsDataDetails JS variable.
    """
    r = cf_requests.get(
        URL,
        impersonate="chrome131",
        timeout=60,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    html = r.text

    m = re.search(r"unitsDataDetails\s*=\s*'(.*?)'\s*;", html, re.DOTALL)
    if not m:
        raise ValueError("Could not find unitsDataDetails in page HTML")

    raw = m.group(1).replace("\\'", "'").replace('\\"', '"')
    details = json.loads(raw)

    two_bed = []
    for fp_id, units in details.items():
        for u in units:
            if u.get("bedroom") == 2 and u.get("bathroom") == 2:
                two_bed.append(u)

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
