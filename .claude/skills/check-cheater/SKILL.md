---
name: check-cheater
description: Check whether an FC 27 Pro Clubs club is on the squad's shared cheater registry (Club Checker), from a typed club name or a screenshot (pre-match lobby, opponent card, full-time result, club search, league table). Use this whenever the user asks if a club cheats, is on the list, has been logged or reported before, "have we played these guys", "are they legit", "check this team", or shares an FC / EA FC / FIFA Clubs screenshot and wants to know who they're up against, even if they never say "check" or "registry". Also use it to list or summarise everyone on the list.
---

# Check a club against the cheater registry

The squad keeps a shared log of cheating Pro Clubs teams ("Club Checker"). It's a claude.ai page with a shared database that club mates also add to, so it can change between checks: always fetch fresh data. Each document in the `reports` collection is one report; the helper script groups reports into clubs and links renamed clubs through their "aka" names.

The user often asks right before kick-off, so be quick and lead with the verdict.

Everything runs from the ClubChecker project root (the folder with `config.json`). `config.json` has `registryUrl` and `ownClubs` (the user's own club names), and `tools/registry.py` does the matching. Read the database with the **ArtifactData** tool; load it with ToolSearch (`select:ArtifactData`) if it isn't available yet.

## 1. Get the club name(s)

**Typed:** use the names as written. Several at once is fine.

**Screenshot** (pasted, a path, or "the latest screenshot", which means `python tools/registry.py latest-screenshot`): read every club name visible, exactly as written. Lobby and result screens show two clubs, one of them the user's; skip any name that loosely matches `ownClubs`. Search results and tables can show many clubs: check them all. If a character is ambiguous (O/0, I/l), go with your best reading, since the matcher treats lookalikes as equal.

If you can't find a club name in the image, say what you can see and ask for the name.

## 2. Fetch the registry

```bash
python tools/registry.py prep-cache
```

Then call ArtifactData `list` with `url` = registryUrl, `collection` = `reports`, `query` = `{"limit": 1000}` and `out_dir` = the printed path. If the result has a `next_cursor`, repeat with `query.cursor` and the same `out_dir`.

## 3. Match

```bash
python tools/registry.py match "<name 1>" ["<name 2>" ...]
```

Use `match --all` to list every flagged club ("who's on the list?").

The matcher ignores case, spacing, punctuation and accents, and treats lookalikes (0/O, 1/I/L, 3/E, 5/S, doubled letters) as equal. It reports:

- **MATCH**: exact, lookalike, or a one-letter typo in a long name. Treat as on the list.
- **POSSIBLE MATCH**: a similar name, or one name contained in the other. It could be a rename, a typo or an unrelated club, so present it as similar and never as a confirmed cheater.
- **NO MATCH**: not on the list.

It also notes when a name looks like one of the user's own clubs.

## 4. Answer

Lead with the verdict for each club, then the evidence that helps the user decide what to do: which cheat, how often, how recently, which players. Use this shape:

**On the list**
> 🟥 **LAG KINGS**: on the list, 3 reports (last 12 Oct 2026)
> Lag switch ×2, Modded players ×1 · players: xLaggerx, Turbo99 · PlayStation
> Latest note: "ball froze every attack"

Use 🟨 for one report and 🟥 for two or more, the same cards the page shows.

**Possible match**
> ❔ **Lag Kings FC**: not on the list by that name, but close to **LAG KINGS** (3 reports, lag switch). Could be the same club renamed.

**Not on the list**
> ✅ **Clean FC**: not on the list.

For several clubs, write one block each with flagged clubs first. Skip empty fields. For screenshots, say how many there are and link the page ([Club Checker](registryUrl)) instead of describing them. If the registry is empty, say the list is empty so far, so the user doesn't read "not on the list" as the club having been vetted.

If the user then says the club cheated, switch to the **register-cheater** skill to log it.
