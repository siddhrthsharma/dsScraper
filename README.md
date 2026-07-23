# DS UCSB Instagram Events Pipeline

Pulls recent posts from the club Instagram once a day and writes `events.json`
for the club site to read. No server — runs entirely on a GitHub Action.

## For the social media person: how to tag an event post

Add the hashtag `#dsevent` anywhere in the caption, then add these lines
(in any order, capitalization doesn't matter):

```
🎉 Join us this week! #dsevent
Event: Intro to Pandas Workshop
When: Oct 5, 2026 6:00pm - 7:30pm
Where: Phelps 1260
```

- `Event:` (or `Title:`) and `When:` (or `Date:`/`Time:`) — required.
- `Where:` (or `Location:`) — optional.
- `Repeats:` (or `Recurring:`) — optional, free text like "Every Tuesday".
- If you forget the tag, an AI model tries to read the caption anyway, but
  it's far less reliable — always use the tag when you can.
- If `When:` is missing or the model can't parse a date, the event still
  shows up on the site as "Date TBA" instead of disappearing.

## How it works

1. `python -m dsscraper.pipeline` fetches recent media from
   `graph.instagram.com`, parses each caption (marker first, Gemini
   fallback), merges into `events.json`, and writes it atomically.
2. `python -m dsscraper.pipeline` never overwrites `events.json` with a
   partial or invalid result — any hard failure leaves the last good file
   in place.
3. `python -m dsscraper.refresh_token` runs after the data step, refreshes
   the ~60-day Instagram access token, and pushes the new value to the
   `IG_ACCESS_TOKEN` GitHub secret via `gh secret set` (stdin only, never
   logged).
4. Both run daily via `.github/workflows/daily.yml`, in that order, so a
   refresh problem never blocks the day's data pull.

## Secrets

| Name | Used by | Notes |
|---|---|---|
| `IG_ACCESS_TOKEN` | pipeline + refresh | `IGAA`-prefixed long-lived token; **rewritten every run** |
| `IG_USER_ID` | pipeline | numeric Instagram user id |
| `GEMINI_API_KEY` | pipeline | Gemini structured-output fallback |
| `GH_PAT_SECRETS` | refresh | fine-grained PAT, `Secrets: write` on this repo — lets the Action update `IG_ACCESS_TOKEN` |
| `META_APP_ID` / `META_APP_SECRET` | *(unused by code)* | kept only for a manual token re-bootstrap; not read by any script here |

## Local development

```bash
pip install -r requirements-dev.txt
pytest -v          # no network calls — everything runs against tests/fixtures
```

To run the pipeline locally against the real API, export the three pipeline
secrets above, set `PYTHONPATH=src`, and run `python -m dsscraper.pipeline`
(for example: `PYTHONPATH=src python -m dsscraper.pipeline`).

## Manual setup checklist

- [ ] Add `GEMINI_API_KEY` as a repo secret.
- [ ] Create a fine-grained PAT with `Secrets: write` on this repo; add it
      as `GH_PAT_SECRETS`. (Without this, the token must be refreshed by
      hand roughly every 55 days.)
- [ ] Confirm the `IGAA` token carries the `instagram_business_basic`
      permission (required for `/media` and for refresh).
- [ ] Repo Settings → Actions → General → Workflow permissions:
      **Read and write permissions** (needed to commit `events.json`).
- [ ] Confirm how the club site reads `events.json` — this pipeline writes
      `{"schema_version": 1, "generated_at": ..., "events": [...]}` (an
      object with an `events` key), not a bare array.
- [ ] Make sure the currently stored `IG_ACCESS_TOKEN` is more than 24
      hours old before the first scheduled refresh runs (refresh requires
      that minimum age).
