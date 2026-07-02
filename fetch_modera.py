import json
import os
import gzip
import time
import urllib.request
from datetime import datetime

SNAPSHOTS_FILE = "data/modera-snapshots.json"
CONFIG_FILE = "gist_config.json"
SIGHTMAP_URL = "https://sightmap.com/app/api/v1/6m9pzr4mwk1/sightmaps/13633"
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
    Fetches Modera West Wash Park 2BR/2BA unit data via the SightMap API.
    No Cloudflare protection — works from any IP including CI.
    """
    req = urllib.request.Request(SIGHTMAP_URL)
    req.add_header("User-Agent", "Mozilla/5.0")
    req.add_header("Accept", "application/json")
    req.add_header("Accept-Encoding", "gzip, deflate")

    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()

    try:
        payload = json.loads(gzip.decompress(raw))
    except Exception:
        payload = json.loads(raw)

    data = payload["data"]

    # Build floor plan map: id -> {plan, bedroom_count, bathroom_count}
    fp_map = {}
    for fp in data["floor_plans"]:
        fp_map[fp["id"]] = {
            "plan": fp["filter_label"],
            "bedrooms": fp.get("bedroom_count", 0),
            "bathrooms": fp.get("bathroom_count", 0),
        }

    # Build floor map: id -> floor number (int)
    floor_map = {}
    for fl in data["floors"]:
        try:
            floor_map[fl["id"]] = int(fl["filter_short_label"])
        except (ValueError, KeyError):
            floor_map[fl["id"]] = 0

    # Filter 2BR/2BA units
    two_bed = []
    for u in data["units"]:
        fp = fp_map.get(u["floor_plan_id"], {})
        if fp.get("bedrooms") == 2 and fp.get("bathrooms") == 2:
            two_bed.append((u, fp))

    if not two_bed:
        raise ValueError("No 2BR/2BA units found in SightMap data")

    today = datetime.now().strftime("%-m/%-d/%Y")
    snapshot = {"date": today, "units": {}}

    for u, fp in two_bed:
        code = str(u["unit_number"])
        sqft = int(u.get("area") or 0)
        avail = u.get("available_on") or ""
        rent = int(u.get("price") or 0)
        floor = floor_map.get(u["floor_id"], int(code) // 100 if code.isdigit() else 0)

        snapshot["units"][code] = {
            "plan": fp["plan"],
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
