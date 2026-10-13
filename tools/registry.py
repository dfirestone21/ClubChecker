#!/usr/bin/env python3
"""Helper for the Club Checker skills (FC 27 Pro Clubs cheater registry).

Reports live in a Supabase database (table "reports") and screenshots in its
"screenshots" storage bucket; the web page and these commands share them.
Connection details come from config.json (supabaseUrl, supabaseKey).

  match NAME [NAME ...]      check club names or gamertags against the registry (fuzzy)
  match --all                list every flagged club
  add --team ... [--file IMG ...]
                             upload screenshots and save a report; files in
                             screenshots/ are deleted once the report is saved
  key NAME                   print the team_key stored for a club name
  latest-screenshot [-n N]   newest images waiting in screenshots/

Name matching mirrors the web page: case, spacing, punctuation and accents are
ignored, and common lookalikes (0/o, 1/l/i, 3/e, 5/s, ...) count as the same.
"""

import argparse
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.json"
INBOX = ROOT / "screenshots"
CONTENT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".webp": "image/webp", ".gif": "image/gif"}
MAX_UPLOAD = 10 * 1024 * 1024  # matches the bucket limit in supabase/setup.sql

# Canonical cheat labels, shared with the web page's chips.
CHEATS = ["Slider hack", "Modded players", "Glitch abuse", "Other"]
CHEAT_ALIASES = {
    "slider": "Slider hack", "sliders": "Slider hack", "sliderhack": "Slider hack",
    "sliderhacks": "Slider hack", "sliderhacking": "Slider hack", "sliderhacker": "Slider hack",
    "mod": "Modded players", "modded": "Modded players", "mods": "Modded players",
    "hack": "Modded players", "hacked": "Modded players", "hacks": "Modded players",
    "hacker": "Modded players", "moddedplayers": "Modded players",
    "glitch": "Glitch abuse", "glitches": "Glitch abuse", "exploit": "Glitch abuse",
    "exploits": "Glitch abuse", "glitchabuse": "Glitch abuse",
    "other": "Other",
}

STRONG = 0.9    # exact, lookalike, or a one-letter typo in a long name
POSSIBLE = 0.7  # worth mentioning as "similar name"

SYMBOLS = str.maketrans({"@": "a", "$": "s", "!": "i", "|": "i", "€": "e"})
LOOKALIKES = str.maketrans("0134578l", "oieastbi")
# Letters that NFKD doesn't decompose into a plain letter plus an accent.
UNACCENT = str.maketrans({"ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "đ": "d", "ł": "l", "þ": "th", "ð": "d", "ı": "i"})


# ---------------------------------------------------------------- names

def fold(name):
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(c for c in s if not unicodedata.category(c).startswith("M"))
    return s.lower().translate(UNACCENT)


def strip(s):
    return re.sub(r"[\W_]+", "", s)


def key(name):
    """Stored team_key: lowercase letters and digits only."""
    return strip(fold(name))


def loose(name):
    """Lookalike-insensitive form used for fuzzy comparison."""
    s = strip(fold(name).translate(SYMBOLS)).translate(LOOKALIKES)
    return re.sub(r"(.)\1+", r"\1", s)


def levenshtein(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def score(query, candidate):
    """Return (score 0..1, kind) for how well candidate matches query."""
    qk, ck = key(query), key(candidate)
    if not qk or not ck:
        return 0.0, ""
    if qk == ck:
        return 1.0, "exact"
    ql, cl = loose(query), loose(candidate)
    if ql == cl:
        return 0.95, "lookalike"
    short, long_ = sorted((ql, cl), key=len)
    sim = 1 - levenshtein(ql, cl) / max(len(ql), len(cl))
    if len(short) >= 4 and short in long_:
        contains = 0.7 + 0.15 * len(short) / len(long_)
        return (sim, "similar") if sim >= contains else (contains, "contains")
    if len(short) <= 4:
        return 0.0, ""  # one letter off in a tiny name is a different name
    return sim, "similar"


# ---------------------------------------------------------------- supabase

def load_config():
    config = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    if not config.get("supabaseUrl") or not config.get("supabaseKey"):
        sys.exit(f"error: set supabaseUrl and supabaseKey in {CONFIG}")
    return config


def api(config, method, path, body=None, raw=None, content_type=None, headers=None):
    """Call the Supabase REST or Storage API and return the parsed JSON reply."""
    key_ = config["supabaseKey"]
    h = {"apikey": key_, "User-Agent": "club-checker"}
    if key_.startswith("eyJ"):  # legacy anon keys are JWTs and also go in Authorization
        h["Authorization"] = f"Bearer {key_}"
    h.update(headers or {})
    data = None
    if raw is not None:
        data, h["Content-Type"] = raw, content_type
    elif body is not None:
        data, h["Content-Type"] = json.dumps(body).encode("utf-8"), "application/json"
    req = urllib.request.Request(config["supabaseUrl"].rstrip("/") + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        sys.exit(f"error: Supabase answered {e.code} to {method} {path.split('?')[0]}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"error: couldn't reach Supabase ({e.reason}). "
                 "If the project is paused, restore it from the Supabase dashboard.")
    return json.loads(text) if text else None


def fetch_reports(config):
    rows, offset = [], 0
    while True:
        page = api(config, "GET", f"/rest/v1/reports?select=*&order=created_at.asc&limit=1000&offset={offset}")
        rows += page
        if len(page) < 1000:
            return rows
        offset += 1000


def upload_screenshot(config, path):
    """Upload one image to the screenshots bucket and return its object name."""
    path = Path(path)
    ctype = CONTENT_TYPES.get(path.suffix.lower())
    if not ctype:
        sys.exit(f"error: {path.name} isn't a PNG, JPG, WebP or GIF")
    data = path.read_bytes()
    if len(data) > MAX_UPLOAD:
        sys.exit(f"error: {path.name} is over 10 MB")
    name = f"{date.today().isoformat()}-{uuid.uuid4().hex[:12]}{path.suffix.lower()}"
    api(config, "POST", f"/storage/v1/object/screenshots/{name}", raw=data, content_type=ctype,
        headers={"x-upsert": "false"})
    return name


def insert_report(config, doc):
    return api(config, "POST", "/rest/v1/reports", body=doc, headers={"Prefer": "return=representation"})[0]


# ---------------------------------------------------------------- grouping

def when(r):
    return r.get("match_date") or (r.get("created_at") or "")[:10]


def group_reports(reports):
    """Group reports into clubs; reports linked through an 'aka' name merge."""
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r in reports:
        keys = [k for k in [key(r["team"])] + [key(a) for a in r.get("aka") or []] if k]
        for k in keys:
            find(k)
        for k in keys[1:]:
            parent[find(k)] = find(keys[0])

    buckets = defaultdict(list)
    for r in reports:
        buckets[find(key(r["team"]))].append(r)

    groups = []
    for rs in buckets.values():
        rs.sort(key=lambda r: (when(r), r.get("created_at") or ""), reverse=True)
        names = []
        for r in rs:
            for n in [r["team"]] + list(r.get("aka") or []):
                if n and key(n) not in {key(x) for x in names}:
                    names.append(n)
        players = []
        for r in rs:
            for p in r.get("players") or []:
                if p not in players:
                    players.append(p)
        groups.append({
            "name": rs[0]["team"],
            "names": names,
            "reports": rs,
            "cheats": Counter(c for r in rs for c in (r.get("cheats") or [])),
            "players": players,
            "platforms": sorted({r["platform"] for r in rs if r.get("platform")}),
            "last_seen": when(rs[0]),
            "first_seen": when(rs[-1]),
        })
    groups.sort(key=lambda g: g["last_seen"], reverse=True)
    return groups


def own_club(name, config):
    best = None
    for club in config.get("ownClubs") or []:
        s, _ = score(name, club)
        if s >= STRONG and (best is None or s > best[0]):
            best = (s, club)
    return best[1] if best else None


# ---------------------------------------------------------------- output

def card(n):
    return "RED CARD" if n >= 2 else "YELLOW CARD"


def describe_group(g, indent="  "):
    n = len(g["reports"])
    aka = [x for x in g["names"] if x != g["name"]]
    lines = [f'{indent}"{g["name"]}"' + (f' (aka {", ".join(aka)})' if aka else "")
             + f" - {n} report{'s' if n != 1 else ''} - {card(n)}"]
    seen = f"last seen {g['last_seen']}"
    if n > 1:
        seen += f", first seen {g['first_seen']}"
    lines.append(f"{indent}  {seen}")
    if g["cheats"]:
        lines.append(f"{indent}  cheats: " + ", ".join(
            f"{c} x{k}" if k > 1 else c for c, k in g["cheats"].most_common()))
    if g["players"]:
        lines.append(f"{indent}  players: " + ", ".join(g["players"]))
    if g["platforms"]:
        lines.append(f"{indent}  platform: " + ", ".join(g["platforms"]))
    lines.append(f"{indent}  reports:")
    for r in g["reports"]:
        bits = [when(r) or "no date"]
        if r.get("team") != g["name"]:
            bits.append(f'as "{r["team"]}"')
        if r.get("cheats"):
            bits.append(" + ".join(r["cheats"]))
        if r.get("score"):
            bits.append(f"score {r['score']}")
        shots = len(r.get("screenshots") or [])
        if shots:
            bits.append(f"{shots} screenshot{'s' if shots != 1 else ''}")
        if r.get("reporter"):
            bits.append(f"by {r['reporter']}")
        lines.append(f"{indent}    - " + " | ".join(bits) + f"  [id {str(r.get('id', ''))[:8]}]")
        if r.get("notes"):
            lines.append(f'{indent}      notes: "{r["notes"]}"')
    return "\n".join(lines)


def summary(groups, reports):
    return (f"Registry: {len(groups)} flagged club{'s' if len(groups) != 1 else ''}, "
            f"{len(reports)} report{'s' if len(reports) != 1 else ''}.")


# ---------------------------------------------------------------- commands

def cmd_match(args):
    config = load_config()
    reports = fetch_reports(config)
    groups = group_reports(reports)
    print(summary(groups, reports) if reports else "Registry: empty so far.")

    if args.all:
        for g in groups:
            print()
            print(describe_group(g, indent=""))
        return

    for name in args.names:
        print()
        print(f'Query: "{name}"')
        mine = own_club(name, config)
        if mine:
            print(f'  NOTE: this looks like one of your own clubs ("{mine}").')
        hits = []
        for g in groups:
            # Club names first so they win ties against gamertags.
            cands = [(n, "") for n in g["names"]] + [(p, " gamertag") for p in g["players"]]
            best = max((score(name, c) + (c, t) for c, t in cands), key=lambda t: t[0])
            if best[0] >= POSSIBLE:
                hits.append((best, g))
        hits.sort(key=lambda h: h[0][0], reverse=True)
        if not hits:
            print("  NO MATCH - no club or gamertag like it in the registry.")
            continue
        for (s, kind, matched, what), g in hits:
            label = "MATCH" if s >= STRONG else "POSSIBLE MATCH"
            via = f' via "{matched}"' if matched != g["name"] else ""
            print(f"  {label} ({kind}{what}, {s:.2f}){via}:")
            print(describe_group(g, indent="    "))


def normalize_cheat(text):
    k = re.sub(r"[^a-z]", "", text.lower())
    if k in CHEAT_ALIASES:
        return CHEAT_ALIASES[k]
    for label in CHEATS:
        if k == re.sub(r"[^a-z]", "", label.lower()):
            return label
    return text.strip()


def split_list(values):
    out = []
    for v in values or []:
        for part in v.split(","):
            part = part.strip()
            if part and part not in out:
                out.append(part)
    return out


def build_report(args):
    team = args.team.strip()
    if not key(team):
        sys.exit("error: --team must contain at least one letter or digit")
    match_date = args.date or date.today().isoformat()
    try:
        date.fromisoformat(match_date)
    except ValueError:
        sys.exit("error: --date must be YYYY-MM-DD")
    cheats = []
    for c in split_list(args.cheat):
        c = normalize_cheat(c)
        if c not in cheats:
            cheats.append(c)
    return {
        "team": team,
        "team_key": key(team),
        "aka": [a for a in split_list(args.aka) if key(a) != key(team)],
        "cheats": cheats,
        "players": split_list(args.player),
        "platform": (args.platform or "").strip(),
        "score": (args.score or "").strip(),
        "match_date": match_date,
        "notes": (args.notes or "").strip(),
        "screenshots": [],
        "reporter": (args.reporter or "").strip(),
        "source": "claude",
    }


def cmd_add(args):
    doc = build_report(args)
    files = [Path(f) for f in args.file or []]
    for f in files:
        if not f.is_file():
            sys.exit(f"error: screenshot not found: {f}")
    if args.dry_run:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        print(f"(dry run: {len(files)} screenshot(s) not uploaded, nothing saved)")
        return

    config = load_config()
    doc["screenshots"] = [upload_screenshot(config, f) for f in files]
    row = insert_report(config, doc)
    print(f"Saved report {row['id'][:8]} for \"{row['team']}\" with {len(doc['screenshots'])} screenshot(s).")

    for f in files:
        if f.resolve().parent == INBOX.resolve():
            f.unlink()
            print(f"Deleted inbox copy: {f.name}")

    reports = fetch_reports(config)
    for g in group_reports(reports):
        if any(r["id"] == row["id"] for r in g["reports"]):
            n = len(g["reports"])
            print(f"\"{g['name']}\" now has {n} report{'s' if n != 1 else ''} - {card(n)}.")
    print(summary(group_reports(reports), reports))
    if config.get("pageUrl"):
        print(f"Page: {config['pageUrl']}")


def cmd_latest_screenshot(args):
    INBOX.mkdir(exist_ok=True)
    files = [p for p in INBOX.iterdir() if p.is_file() and p.suffix.lower() in CONTENT_TYPES]
    if not files:
        print(f"No screenshots waiting in {INBOX}")
        return
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files[: args.n]:
        stamp = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"{stamp}  {p}")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("match", help="check club names against the registry")
    m.add_argument("names", nargs="*")
    m.add_argument("--all", action="store_true", help="list every flagged club")
    m.set_defaults(fn=cmd_match)

    a = sub.add_parser("add", help="upload screenshots and save a report")
    a.add_argument("--team", required=True, help="club name exactly as shown in game")
    a.add_argument("--aka", action="append", help="other names for the same club (repeatable or comma-separated)")
    a.add_argument("--cheat", action="append", help=f"cheat type, e.g. {', '.join(CHEATS)}")
    a.add_argument("--player", action="append", help="gamertag of a cheating player")
    a.add_argument("--platform", help="PlayStation, Xbox or PC")
    a.add_argument("--score", help="final score from your side, e.g. 1-4")
    a.add_argument("--date", help="match date YYYY-MM-DD (default today)")
    a.add_argument("--notes", help="free-text notes")
    a.add_argument("--reporter", help="who's logging it, shown as 'Logged by ...'")
    a.add_argument("--file", action="append", help="screenshot to upload (repeatable)")
    a.add_argument("--dry-run", action="store_true", help="print the report without uploading or saving")
    a.set_defaults(fn=cmd_add)

    k = sub.add_parser("key", help="print the team_key for a club name")
    k.add_argument("name")
    k.set_defaults(fn=lambda args: print(key(args.name)))

    s = sub.add_parser("latest-screenshot", help="newest images waiting in screenshots/")
    s.add_argument("-n", type=int, default=1, help="how many to list (default 1)")
    s.set_defaults(fn=cmd_latest_screenshot)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
