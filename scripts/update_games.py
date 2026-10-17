#!/usr/bin/env python3
"""Free game deals updater.

- Fetches current free-game deals from Epic Games Store and GamerPower.
- Merges them into games.json. Entries WITHOUT "source": "auto" are manual and are never touched.
- Sends one Firebase Cloud Messaging push (topic "free-games") for newly active games.

Dates in games.json are Sri Lanka time (UTC+05:30), written as 2026-10-09T22:30:00.
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GAMES_FILE = ROOT / "games.json"
NOTIFIED_FILE = ROOT / "notified.json"
LKT = timezone(timedelta(hours=5, minutes=30))
FMT = "%Y-%m-%dT%H:%M:%S"
TOPIC = "free-games"
UA = {"User-Agent": "Mozilla/5.0 (free-game-deals-bot)"}

PLATFORM_NAMES = {
    "steam": "Steam",
    "epic": "Epic Games",
    "gog": "GOG",
    "ubisoft": "Ubisoft",
    "itch": "itch.io",
}
PLATFORM_PATTERNS = {
    "steam": r"\bsteam\b",
    "epic": r"\bepic\b",
    "gog": r"\bgog\b",
    "ubisoft": r"\bubisoft\b",
    "itch": r"\bitch(\.io)?\b",
}


# ---------- helpers ----------
def fetch_json(url):
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (attempt + 1))
    raise last


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_dt(s):
    """Parse an ISO date; naive values are treated as Sri Lanka time."""
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=LKT)


def to_lkt(d):
    return d.astimezone(LKT).strftime(FMT) if d else None


def game_key(g):
    return (g.get("platform", ""), re.sub(r"[^a-z0-9]", "", g.get("title", "").lower()))


def game_id(g):
    return g.get("id") or f"{g.get('platform', 'other')}-{slugify(g.get('title', ''))}"


def make_entry(platform, title, image, description, claim_url, start, end, feed):
    entry = {
        "id": f"{platform}-{slugify(title)}",
        "platform": platform,
        "title": title,
        "image": image or "",
        "description": (description or "").strip()[:300],
        "claimUrl": claim_url,
        "startDate": to_lkt(start),
        "endDate": to_lkt(end),
        "source": "auto",
        "feed": feed,
    }
    return entry


def is_active(g, now):
    s, e = parse_dt(g.get("startDate")), parse_dt(g.get("endDate"))
    return (not s or s <= now) and (not e or e > now)


# ---------- feeds ----------
def fetch_epic():
    url = (
        "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
        "?locale=en-US&country=LK&allowCountries=LK"
    )
    data = fetch_json(url)
    out = []
    for el in data["data"]["Catalog"]["searchStore"]["elements"]:
        window = None
        for group in (el.get("promotions") or {}).get("promotionalOffers") or []:
            for o in group.get("promotionalOffers", []):
                if (o.get("discountSetting") or {}).get("discountPercentage") == 0:
                    window = o
        if not window:
            continue
        title = (el.get("title") or "").strip()
        if not title or "mystery" in title.lower():
            continue
        slug = None
        mappings = (el.get("offerMappings") or []) + ((el.get("catalogNs") or {}).get("mappings") or [])
        for m in mappings:
            if m.get("pageSlug"):
                slug = m["pageSlug"]
                break
        slug = slug or el.get("productSlug") or el.get("urlSlug")
        claim = (
            f"https://store.epicgames.com/en-US/p/{slug.split('/')[0]}"
            if slug
            else "https://store.epicgames.com/en-US/free-games"
        )
        imgs = {i.get("type"): i.get("url") for i in el.get("keyImages") or []}
        image = (
            imgs.get("OfferImageWide")
            or imgs.get("DieselStoreFrontWide")
            or imgs.get("Thumbnail")
            or next(iter(imgs.values()), "")
        )
        out.append(
            make_entry(
                "epic", title, image, el.get("description"), claim,
                parse_dt(window.get("startDate")), parse_dt(window.get("endDate")), "epic",
            )
        )
    return out


def clean_title(t):
    t = re.sub(
        r"\s*\((?:steam|epic games(?: store)?|gog|ubisoft(?: connect)?|itch\.io)[^)]*\)",
        "", t, flags=re.I,
    )
    t = re.sub(r"\s+giveaway$", "", t, flags=re.I)
    return t.strip()


def parse_gp_date(s):
    if not s or s.strip().upper() == "N/A":
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def fetch_gamerpower():
    data = fetch_json("https://www.gamerpower.com/api/giveaways?type=game&sort-by=date")
    out = []
    if not isinstance(data, list):  # API returns an object when there are no results
        return out
    for g in data:
        if g.get("status") != "Active":
            continue
        plats = (g.get("platforms") or "").lower()
        platform = next((p for p, pat in PLATFORM_PATTERNS.items() if re.search(pat, plats)), None)
        if not platform:
            continue
        title = clean_title(g.get("title", ""))
        if not title:
            continue
        out.append(
            make_entry(
                platform, title, g.get("image") or g.get("thumbnail"), g.get("description"),
                g.get("open_giveaway_url") or g.get("gamerpower_url") or "",
                parse_gp_date(g.get("published_date")), parse_gp_date(g.get("end_date")), "gamerpower",
            )
        )
    return out


# ---------- push ----------
def send_push(games, creds_json):
    import firebase_admin
    from firebase_admin import credentials, messaging

    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(credentials.Certificate(json.loads(creds_json)))

    if len(games) == 1:
        g = games[0]
        title = f"🎮 Free on {PLATFORM_NAMES.get(g['platform'], g['platform'].title())}: {g['title']}"
        end = parse_dt(g.get("endDate"))
        body = (
            f"Free until {end.astimezone(LKT).strftime('%b %d, %I:%M %p')}"
            if end
            else "Free for a limited time. Claim it now!"
        )
        image = g.get("image") if str(g.get("image", "")).startswith("http") else None
    else:
        title = f"🎮 {len(games)} new free games"
        body = ", ".join(g["title"] for g in games[:4]) + ("…" if len(games) > 4 else "")
        image = None

    msg = messaging.Message(
        topic=TOPIC,
        notification=messaging.Notification(title=title, body=body, image=image),
        android=messaging.AndroidConfig(priority="high"),
    )
    try:
        messaging.send(msg)
        print(f"Push sent: {title}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"! Push failed: {e}", file=sys.stderr)
        return False


# ---------- main ----------
def main():
    now = datetime.now(LKT)

    try:
        existing = json.loads(GAMES_FILE.read_text("utf-8")) if GAMES_FILE.exists() else []
    except json.JSONDecodeError as e:
        print(f"games.json is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    manual = [g for g in existing if g.get("source") != "auto"]
    old_auto = [g for g in existing if g.get("source") == "auto"]

    fetched, failed = [], set()
    for feed, fn in (("epic", fetch_epic), ("gamerpower", fetch_gamerpower)):
        try:
            fetched += fn()
            print(f"{feed}: ok")
        except Exception as e:  # noqa: BLE001
            print(f"! {feed} failed: {e}", file=sys.stderr)
            failed.add(feed)
    # If a feed is down, keep its previous entries instead of wiping them.
    fetched += [g for g in old_auto if g.get("feed") in failed]

    seen = {game_key(g) for g in manual}
    auto = []
    for g in fetched:
        end = parse_dt(g.get("endDate"))
        if end and end <= now:
            continue
        k = game_key(g)
        if k in seen:
            continue
        seen.add(k)
        auto.append(g)
    auto.sort(key=lambda g: (g.get("endDate") or "9999", g["title"]))
    result = manual + auto

    new_text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    old_text = GAMES_FILE.read_text("utf-8") if GAMES_FILE.exists() else ""
    if new_text != old_text:
        GAMES_FILE.write_text(new_text, "utf-8")
        print(f"games.json updated ({len(manual)} manual, {len(auto)} auto)")
    else:
        print("games.json unchanged")

    # ----- notifications -----
    first_run = not NOTIFIED_FILE.exists()
    notified = set(json.loads(NOTIFIED_FILE.read_text("utf-8"))) if not first_run else set()
    creds = os.environ.get("FIREBASE_SERVICE_ACCOUNT", "").strip()
    fresh = [g for g in result if is_active(g, now) and game_id(g) not in notified]
    if fresh:
        if first_run or not creds:
            reason = "first run" if first_run else "no FIREBASE_SERVICE_ACCOUNT secret"
            print(f"Marking {len(fresh)} game(s) as seen without push ({reason})")
            notified |= {game_id(g) for g in fresh}
        elif send_push(fresh, creds):
            notified |= {game_id(g) for g in fresh}
    notified &= {game_id(g) for g in result} | {game_id(g) for g in fresh if game_id(g) in notified}
    out = json.dumps(sorted(notified), indent=2) + "\n"
    if not NOTIFIED_FILE.exists() or NOTIFIED_FILE.read_text("utf-8") != out:
        NOTIFIED_FILE.write_text(out, "utf-8")


if __name__ == "__main__":
    main()
