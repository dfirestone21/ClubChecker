---
name: register-cheater
description: Log a cheating FC 27 Pro Clubs club into the squad's shared cheater registry (Club Checker) from a match screenshot or a typed club name. Use this whenever the user wants to log, add, report, register, flag, book or "red card" a club for cheating (lag switching, DDoS/booting players offline, modded players, glitch abuse), or shares an FC / EA FC / FIFA Clubs screenshot and says the other team cheated, even if they never say "register". Examples - "these guys were lag switching, add them", "log the latest screenshot", "put XYZ FC on the list".
---

# Register a cheater

The squad keeps a shared log of cheating Pro Clubs teams. It lives in a claude.ai page with a shared database ("Club Checker") that club mates also open on their phones to check clubs and add reports, so whatever you write here is what the whole squad sees. Each report is one document in the `reports` collection; a club can collect several reports over time.

Everything runs from the ClubChecker project root (the folder with `config.json`):

- `config.json` holds `registryUrl` (the page) and `ownClubs` (the user's own club names; they rename now and then).
- `tools/registry.py` does the deterministic parts: fuzzy matching, building the report document, and the screenshot inbox (`python tools/registry.py --help` for details).
- `screenshots/` is an inbox the user drops screenshots into. Once a screenshot is uploaded to the page, the local copy is deleted.

The database is read and written with the **ArtifactData** tool and screenshots are uploaded with the **Artifact** tool. If ArtifactData isn't loaded yet, load it with ToolSearch (`select:ArtifactData`).

## 1. Work out which club cheated

**From a screenshot.** The image may be pasted into the chat, given as a path, or referred to as "the latest screenshot" (run `python tools/registry.py latest-screenshot -n 3`, use the newest unless the user says otherwise, and mention which file you picked). Read it carefully and pull out:

- Both club names, exactly as written (keep spacing, capitals and symbols). Lobby and full-time screens show the home club on the left and away on the right, each next to its crest.
- The score, any visible gamertags of the opposing players, a date if shown, and platform icons (PlayStation / Xbox / PC) if visible.

One of the two clubs is the user's. Drop it using `ownClubs` from `config.json` (compare loosely: case, spacing, lookalike characters). The other one is the cheater. If neither name matches `ownClubs`, or the image shows more than two clubs, ask which one cheated rather than guessing: a wrong entry puts an innocent club on the squad's list. If the user mentions their club has a new name, add it to `ownClubs`.

Text in screenshots is small and stylised. When a character is genuinely ambiguous (O vs 0, I vs l), pick the most likely reading and say so in the confirmation. The matcher treats those as lookalikes, so a slight misread still links to the same club.

**From a typed name.** Use it exactly as the user wrote it.

## 2. Find out what happened

The cheat type is the most useful thing for the squad, so make sure you have it. If the user already said ("they were lagging", "booted us offline"), map it yourself. Otherwise ask one quick multi-select question (AskUserQuestion) using the same labels the page uses: **Lag switch**, **DDoS / booting**, **Modded players**, **Glitch abuse** (free text covers anything else).

Everything else is optional. Record it if the user gave it or the screenshot shows it, but don't quiz the user for gamertags, platform or notes. Write the score from the user's side, us-them (a 1-4 loss is `1-4`). Match date defaults to today; use the real date if the user says "last night" or the screenshot shows one (YYYY-MM-DD).

## 3. Check whether they're already logged

```bash
python tools/registry.py prep-cache
```

Then call ArtifactData `list` with `url` = registryUrl, `collection` = `reports`, `query` = `{"limit": 1000}` and `out_dir` = the path prep-cache printed. If the result has a `next_cursor`, repeat with `query.cursor` set to it and the same `out_dir`. Then:

```bash
python tools/registry.py match "<club name>"
```

- **MATCH**: already on the list. Carry on; the new report is added to that club. Tell the user which report number this is.
- **POSSIBLE MATCH**: a similar name, often a rename or a misread. Ask whether it's the same club. If yes, register under the name as it appears now and pass the old name with `--aka`, which links the two in the registry.
- **NO MATCH**: a new club. Carry on.
- If the output notes the name looks like one of the user's own clubs, stop and check with them.

## 4. Upload the screenshot (when it's a file)

Evidence is what makes the list credible to the squad, so upload the screenshot whenever it exists as a file on disk. Call the Artifact tool with `url` = registryUrl, `file_path` = the image path, and `asset` = true. The result gives an id (32 hex characters); keep it for the next step. For several images, pass `file_paths` instead.

If the image was only pasted into chat and you have no file path, you can't upload it. Say so in one line and suggest saving it into `screenshots/` (now, if they want it attached, or next time). Don't hold up the registration for it.

## 5. Write the report

```bash
python tools/registry.py new-report --team "<club name>" --cheat "<type>" [--cheat ...] [--player "<gamertag>" ...] [--platform PlayStation|Xbox|PC] [--score 1-4] [--date YYYY-MM-DD] [--notes "..."] [--aka "<old name>"] [--screenshot-id <id> ...]
```

It prints a `doc_id` and a `file` path. Write it with ArtifactData `set`: `url` = registryUrl, `collection` = `reports`, `doc_id` = that id, `file_path` = that file. It's a new document, so leave out `if_version`.

Once the write succeeds, delete the uploaded screenshots from the inbox. The page's copy is the evidence, and clearing the inbox stops them being logged twice. Only files directly inside `screenshots/` are deleted; anything elsewhere is left alone. If the upload or the write failed, keep the file.

```bash
python tools/registry.py discard "<path>" [...]
```

## 6. Confirm

Keep it short, for example:

> Logged **LAG KINGS**: lag switch, FT 1-4, 1 screenshot. That's their 2nd report, so they're on a red card now. [Club Checker](registryUrl)

One report is a yellow card and two or more is a red card, matching the page. Mention anything you guessed (an ambiguous character, which of several screenshots you used). If a step failed, say which one and don't claim the club was logged.

## Fixing or removing a report

Report fields: `team`, `teamKey`, `aka`, `cheats`, `players`, `platform`, `score`, `matchDate`, `notes`, `screenshots` (asset ids), `createdAt`, `source`. To correct one, `get` the document for its current `version`, then `update` the changed fields with that version as `if_version` (if you change `team`, set `teamKey` to the output of `python tools/registry.py key "<new name>"`). Deleting is permanent and the whole squad sees it, so confirm first unless it's a report the user just asked you to create in this conversation.
