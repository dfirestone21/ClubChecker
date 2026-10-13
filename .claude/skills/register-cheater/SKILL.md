---
name: register-cheater
description: Log a cheating FC 27 Pro Clubs club into the squad's shared cheater registry (Club Checker) from a match screenshot or a typed club name. Use this whenever the user wants to log, add, report, register, flag, book or "red card" a club for cheating (slider hacks, modded players, glitch abuse or any other hack), or shares an FC / EA FC / FIFA Clubs screenshot and says the other team cheated, even if they never say "register". Examples - "these guys were using slider hacks, add them", "log the latest screenshot", "put XYZ FC on the list".
---

# Register a cheater

The squad keeps a shared log of cheating Pro Clubs teams on the Club Checker page (`pageUrl` in `config.json`). Anyone with the link can check clubs and add reports, so whatever you save is what the whole squad sees. Reports can't be edited or deleted from here (only from the Supabase dashboard), so get the details right before saving.

Everything runs from the ClubChecker project root (the folder with `config.json`):

- `config.json` holds `pageUrl`, the Supabase connection details, and `ownClubs` (the user's own club names; they rename now and then).
- `tools/registry.py` checks and saves reports (`python tools/registry.py --help` for details).
- `screenshots/` is an inbox the user can drop screenshots into. Once a report is saved, its screenshots are deleted from the inbox; the page keeps its own copy.

## 1. Work out which club cheated

**From a screenshot.** The image may be pasted into the chat (it usually comes with its file path), given as a path, or referred to as "the latest screenshot" (run `python tools/registry.py latest-screenshot -n 3`, use the newest unless the user says otherwise, and mention which file you picked). Read it carefully and pull out:

- Both club names, exactly as written (keep spacing, capitals and symbols). Lobby and full-time screens show the home club on the left and away on the right, each next to its crest.
- The score, any visible gamertags of the opposing players, a date if shown, and platform icons (PlayStation / Xbox / PC) if visible.

One of the two clubs is the user's. Drop it using `ownClubs` from `config.json` (compare loosely: case, spacing, lookalike characters). The other one is the cheater. If neither name matches `ownClubs`, or the image shows more than two clubs, ask which one cheated rather than guessing: a wrong entry puts an innocent club on the squad's list. If the user mentions their club has a new name, add it to `ownClubs`.

Tracker sites list players under a match; check whose players they are before recording them. If it's unclear whether they belong to the cheating club, leave them out and mention them in the confirmation instead of putting possibly innocent gamertags on the list.

Text in screenshots is small and stylised. When a character is genuinely ambiguous (O vs 0, I vs l), pick the most likely reading and say so in the confirmation. The matcher treats those as lookalikes, so a slight misread still links to the same club.

**From a typed name.** Use it exactly as the user wrote it.

## 2. Find out what happened

The cheat type is the most useful thing for the squad, so make sure you have it. If the user already said ("slider hack", "their players were modded"), map it yourself; anything that doesn't fit a label is recorded in their words (e.g. "Unknown hack"). Otherwise ask one quick multi-select question (AskUserQuestion) using the same labels the page uses: **Slider hack**, **Modded players**, **Glitch abuse** (free text covers anything else).

Everything else is optional. Record it if the user gave it or the screenshot shows it, but don't quiz the user for gamertags, platform or notes. Write the score from the user's side, us-them (a 1-4 loss is `1-4`); leave it out if you can't tell which side was theirs. Match date defaults to today; use the real date if the user says "last night" or the screenshot shows one (YYYY-MM-DD).

## 3. Check whether they're already logged

```bash
python tools/registry.py match "<club name>"
```

- **MATCH**: already on the list. Carry on; the new report is added to that club.
- **POSSIBLE MATCH**: a similar name, often a rename or a misread. Ask whether it's the same club. If yes, register under the name as it appears now and pass the old name with `--aka`, which links the two in the registry.
- **NO MATCH**: a new club. Carry on.
- If the output notes the name looks like one of the user's own clubs, stop and check with them.

## 4. Save the report

```bash
python tools/registry.py add --team "<club name>" --cheat "<type>" [--cheat ...] [--player "<gamertag>" ...] [--platform PlayStation|Xbox|PC] [--score 1-4] [--date YYYY-MM-DD] [--notes "..."] [--aka "<old name>"] [--file "<screenshot path>" ...]
```

`add` uploads the screenshots, saves the report, deletes uploaded files that were in `screenshots/` (files elsewhere are left alone), and prints how many reports the club now has. Attach the screenshot whenever you have it as a file: evidence is what makes the list credible. If an image was pasted without a file path, you can't attach it; say so in one line and suggest dropping it into `screenshots/` next time.

Pass `--reporter "<name>"` only if the user tells you who's logging it; it shows as "Logged by …" on the page. Without it the page says "Logged via Claude".

If `add` fails, nothing was saved (or only screenshots were uploaded). Report the error and don't claim the club was logged.

## 5. Confirm

Keep it short, for example:

> Logged **LAG KINGS**: slider hack, FT 1-4, 1 screenshot. That's their 2nd report, so they're on a red card now. [Club Checker](pageUrl)

One report is a yellow card and two or more is a red card, matching the page. Mention anything you guessed (an ambiguous character, which of several screenshots you used, players you left out).

## Fixing or removing a report

The public key can only add reports, so neither you nor the page can edit or delete one. If the user wants a report changed or removed, point them to the Supabase dashboard: **Table Editor → reports** to edit cells or delete the row, and **Storage → screenshots** to delete images. The project ref is the subdomain of `supabaseUrl`, so the link is `https://supabase.com/dashboard/project/<ref>/editor`. A follow-up detail (a gamertag they remembered later) can instead go in as a new report if they prefer.
