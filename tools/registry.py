#!/usr/bin/env python3
"""Local helper for the Club Checker skills (FC 27 Pro Clubs cheater registry).

The registry lives in a shared claude.ai artifact database (collection
"reports"), which Claude reads and writes with the ArtifactData tool. This
script handles the deterministic parts around those calls:

  prep-cache                 empty the local cache folder and print its path
                             (pass it as ArtifactData's out_dir when listing)
  match NAME [NAME ...]      fuzzy-match club names against the cached reports
  match --all                list every flagged club in the cache
  new-report --team ...      build a report document to write with ArtifactData
  key NAME                   print the teamKey stored for a club name
  latest-screenshot [-n N]   newest images in screenshots/ not yet logged
  discard PATH [PATH ...]    delete screenshots from screenshots/ once uploaded

Name matching mirrors the web page: case, spacing, punctuation and accents are
ignored, and common lookalikes (0/o, 1/l/i, 3/e, 5/s, ...) count as the same.
"""

import argparse
import json
import re
import secrets
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.json"
CACHE = ROOT / ".cache" / "registry"
OUTGOING = ROOT / ".cache" / "outgoing"
INBOX = ROOT / "screenshots"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# Canonical cheat labels, shared with the web page's chips.
CHEATS = ["Lag switch", "DDoS / booting", "Modded players", "Glitch abuse", "Other"]
CHEAT_ALIASES = {
    "lag": "Lag switch", "lagswitch": "Lag switch", "lagging": "Lag switch",
    "lagswitching": "Lag switch", "connection": "Lag switch",
    "ddos": "DDoS / booting", "dos": "DDoS / booting", "boot": "DDoS / booting",
    "booting": "DDoS / booting", "booted": "DDoS / booting", "kicked": "DDoS / booting",
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
    """Stored teamKey: lowercase letters and digits only."""
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


# ---------------------------------------------------------------- data

def load_config():
    if not CONFIG.exists():
        return {"registryUrl": "", "ownClubs": []}
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def unwrap(obj):
    """Accept either a bare report body or a {data: {...}} wrapper."""
    if isinstance(obj, dict) and "team" not in obj and isinstance(obj.get("data"), dict):
        return obj["data"]
    return obj


def load_reports():
    folder = CACHE / "reports"
    reports = []
    if not folder.exists():
        return reports
    for f in sorted(folder.glob("*.json")):
        try:
            body = unwrap(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as e:
            print(f"warning: skipped unreadable {f.name}: {e}", file=sys.stderr)
            continue
        if not isinstance(body, dict) or not body.get("team"):
            continue
        body["_id"] = f.stem
        reports.append(body)
    return reports


def when(r):
    return r.get("matchDate") or (r.get("createdAt") or "")[:10]


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
        rs.sort(key=lambda r: (when(r), r.get("createdAt") or ""), reverse=True)
        names = []
        for r in rs:
            for n in [r["team"]] + list(r.get("aka") or []):
                if n and key(n) not in {key(x) for x in names}:
                    names.append(n)
        cheats = Counter(c for r in rs for c in (r.get("cheats") or []))
        players = []
        for r in rs:
            for p in r.get("players") or []:
                if p not in players:
                    players.append(p)
        platforms = sorted({r["platform"] for r in rs if r.get("platform")})
        groups.append({
            "name": rs[0]["team"],
            "names": names,
            "reports": rs,
            "cheats": cheats,
            "players": players,
            "platforms": platforms,
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
        lines.append(f"{indent}    - " + " | ".join(bits) + f"  [id {r['_id']}]")
        if r.get("notes"):
            lines.append(f'{indent}      notes: "{r["notes"]}"')
    return "\n".join(lines)


# ---------------------------------------------------------------- commands

def cmd_prep_cache(_args):
    if CACHE.exists():
        shutil.rmtree(CACHE)
    CACHE.mkdir(parents=True)
    print(CACHE)


def cmd_match(args):
    config = load_config()
    reports = load_reports()
    groups = group_reports(reports)
    if not reports:
        print(f"No reports in the local cache ({CACHE}).")
        print("If you haven't fetched yet: run prep-cache, then ArtifactData list on "
              "collection 'reports' with out_dir set to that path. Otherwise the registry is empty.")
        if not args.names:
            return
    else:
        print(f"Registry: {len(groups)} flagged club{'s' if len(groups) != 1 else ''}, "
              f"{len(reports)} report{'s' if len(reports) != 1 else ''}.")

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
            best = max((score(name, n) + (n,) for n in g["names"]), key=lambda t: t[0])
            if best[0] >= POSSIBLE:
                hits.append((best, g))
        hits.sort(key=lambda h: h[0][0], reverse=True)
        if not hits:
            print("  NO MATCH - not in the registry.")
            continue
        for (s, kind, matched), g in hits:
            label = "MATCH" if s >= STRONG else "POSSIBLE MATCH"
            via = f' via "{matched}"' if matched != g["name"] else ""
            print(f"  {label} ({kind}, {s:.2f}){via}:")
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


def cmd_new_report(args):
    team = args.team.strip()
    if not key(team):
        sys.exit("error: --team must contain at least one letter or digit")
    match_date = args.date or date.today().isoformat()
    try:
        date.fromisoformat(match_date)
    except ValueError:
        sys.exit("error: --date must be YYYY-MM-DD")
    now = datetime.now(timezone.utc)
    doc_id = f"r{now.strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(2)}"
    cheats = []
    for c in split_list(args.cheat):
        c = normalize_cheat(c)
        if c not in cheats:
            cheats.append(c)
    doc = {
        "team": team,
        "teamKey": key(team),
        "aka": [a for a in split_list(args.aka) if key(a) != key(team)],
        "cheats": cheats,
        "players": split_list(args.player),
        "platform": (args.platform or "").strip(),
        "score": (args.score or "").strip(),
        "matchDate": match_date,
        "notes": (args.notes or "").strip(),
        "screenshots": split_list(args.screenshot_id),
        "createdAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "claude",
    }
    OUTGOING.mkdir(parents=True, exist_ok=True)
    path = OUTGOING / f"{doc_id}.json"
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"doc_id: {doc_id}")
    print(f"file:   {path}")
    print(json.dumps(doc, indent=2, ensure_ascii=False))


def cmd_latest_screenshot(args):
    INBOX.mkdir(exist_ok=True)
    files = [p for p in INBOX.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    if not files:
        print(f"No screenshots waiting in {INBOX}")
        return
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files[: args.n]:
        stamp = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"{stamp}  {p}")


def cmd_discard(args):
    for raw in args.paths:
        src = Path(raw)
        if not src.exists():
            print(f"skipped (not found): {src}")
            continue
        if src.resolve().parent != INBOX.resolve():
            print(f"left in place (outside screenshots/): {src}")
            continue
        src.unlink()
        print(f"deleted: {src.name}")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("prep-cache", help="empty the cache folder and print its path").set_defaults(fn=cmd_prep_cache)

    m = sub.add_parser("match", help="fuzzy-match club names against the cached reports")
    m.add_argument("names", nargs="*")
    m.add_argument("--all", action="store_true", help="list every flagged club")
    m.set_defaults(fn=cmd_match)

    n = sub.add_parser("new-report", help="build a report document for ArtifactData set")
    n.add_argument("--team", required=True, help="club name exactly as shown in game")
    n.add_argument("--aka", action="append", help="other names for the same club (repeatable or comma-separated)")
    n.add_argument("--cheat", action="append", help=f"cheat type, e.g. {', '.join(CHEATS)}")
    n.add_argument("--player", action="append", help="gamertag of a cheating player")
    n.add_argument("--platform", help="PlayStation, Xbox or PC")
    n.add_argument("--score", help="final score from your side, e.g. 1-4")
    n.add_argument("--date", help="match date YYYY-MM-DD (default today)")
    n.add_argument("--notes", help="free-text notes")
    n.add_argument("--screenshot-id", action="append", help="asset id from the screenshot upload")
    n.set_defaults(fn=cmd_new_report)

    k = sub.add_parser("key", help="print the teamKey for a club name")
    k.add_argument("name")
    k.set_defaults(fn=lambda a: print(key(a.name)))

    s = sub.add_parser("latest-screenshot", help="newest images waiting in screenshots/")
    s.add_argument("-n", type=int, default=1, help="how many to list (default 1)")
    s.set_defaults(fn=cmd_latest_screenshot)

    d = sub.add_parser("discard", help="delete uploaded screenshots from screenshots/")
    d.add_argument("paths", nargs="+")
    d.set_defaults(fn=cmd_discard)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
