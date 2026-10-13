# Club Checker

A shared cheater log for FC 27 Pro Clubs. Log a cheating club straight from a screenshot, then check any club before kick-off, from Claude Code or from your phone.

<img src="docs/club-checker.png" alt="The Club Checker page: a search box and a list of flagged clubs, each with a yellow card and its cheat type" width="560">

## How it works

The log lives in a **claude.ai page with a built-in shared database**. Your squad opens it to search clubs, see each report with its screenshots and gamertags, and log new cheaters. A club with one report gets a yellow card; two or more get a red card.

Two **Claude Code skills** read and write the same database:

- **`register-cheater`** reads the club name, score and date from a screenshot (or takes a typed name), asks what the cheat was if you didn't say, uploads the screenshot as evidence and saves the report.
- **`check-cheater`** tells you whether a club is on the list, from a typed name or a lobby screenshot, along with what they did, how often and which players.

Matching is forgiving: it ignores caps, spaces and accents, treats lookalikes (0/O, 1/I/l, 5/S, ø/o) as the same letter, and links clubs that renamed through their old names.

## Usage

Open a Claude Code session in this folder, then either call a skill directly or just ask:

```text
/register-cheater   the left team, they were lag switching     (with a screenshot)
/check-cheater      is Deportivo KNG on the list?
log the latest screenshot, slider hack
are these guys legit?                                          (with a lobby screenshot)
```

Paste screenshots into the chat or drop them into `screenshots/`. Once a screenshot is uploaded to the page, the local copy is deleted.

## Setup

- [Claude Code](https://claude.com/claude-code). The skills in `.claude/skills/` load in any session opened in this folder.
- Python 3, with no extra packages.
- `config.json`:
  - `registryUrl`: the Club Checker page.
  - `ownClubs`: your club names, so the skills know which side of a screenshot is yours. Update it when you rename.

## Sharing with your squad

The page is private until you share it. In the page's **Share** menu, invite mates by email as **Editors** so they can add reports and screenshots; Viewers can only check clubs. Don't turn on a public link: it removes write access for people invited from outside your account.

## Project layout

```text
.claude/skills/register-cheater/   skill: log a cheater
.claude/skills/check-cheater/      skill: check a club
tools/registry.py                  name matching, report builder, screenshot inbox
web/club-checker.html              source of the shared page
config.json                        page URL and your club names
```

To change the page, edit `web/club-checker.html` and ask Claude to republish it to the URL in `config.json`. Reports and screenshots are stored in the page's database, so republishing keeps them.
