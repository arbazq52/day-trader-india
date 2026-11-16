---
name: trader-entry
description: >-
  Entry Timer. Watches a setup bar by bar and tells you the moment to get in.
  Reads free Yahoo 1-minute or 5-minute bars, builds the opening range (the
  first 15 minutes by default) and calls the entry on the first completed bar
  that CLOSES above the range high, or above a level you give it (like a
  20-day high from the scanner), with an optional volume check. Says waiting
  and how far, triggered with the time and the price, expired, or not open
  yet, and writes trader/entry.json for /trader-exit. India edition: NSE cash
  equities, Yahoo SYMBOL.NS bars, session 9:15 AM to 3:30 PM IST, prices in
  rupees. Long side only. It never places an order. Use when the user says
  "tell me when to get in", "watch RELIANCE", "has it broken out", "did it break the opening range", "entry
  signal", "time my entry", "check my watchlist", or after /trader-scanner
  and /trader-news, before /trader-exit.
argument-hint: "[SYMBOL] [--setup orb|level] [--interval 5m|1m]"
---

# trader-entry

The Entry Timer turns a setup into one moment: the bar that confirms it. It
reads bars, 1-minute or 5-minute, and waits for each one to finish. A price
that pokes above the high in the middle of a bar is not an entry. A bar that
CLOSES above it is. Then it says the time and the price, writes them down for
the Exit Planner, and stops. It never buys anything. Day trading loses most
people money, and a clean signal does not change that.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE             # 15-minute opening range, 5-minute bars
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE --write     # also save trader/entry.json
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE --setup level --level 1325.50
python3 "${CLAUDE_SKILL_DIR}/entry.py" check RELIANCE --interval 1m --min-volume-x 1.5
python3 "${CLAUDE_SKILL_DIR}/entry.py" watch RELIANCE --until 15:00 # one line per closed bar, stops on the trigger
python3 "${CLAUDE_SKILL_DIR}/entry.py" watchlist                   # every hit in trader/watchlist.json
```

Other flags: `--or-minutes N` (default 15), `--json`, `--offline FILE` (a
saved Yahoo chart JSON, `.json` or `.json.gz`, or a folder of
`<SYMBOL>.json`), `--now "2026-11-16 10:15"` (IST) to replay a day.
Symbols are plain NSE symbols (`RELIANCE`, `M&M`, `BAJAJ-AUTO`); the script
asks Yahoo for `SYMBOL.NS`. `watch` with `--now` or `--offline` runs on a simulated clock and replays the
day bar by bar without waiting.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/watchlist.json` | the scanner's hits (`hits[].symbol`), for `watchlist` |
| `trader/config.json` | `no_entries_before` (09:30, when the range is done) and `no_entries_after` (15:00), IST. Optional |
| Yahoo chart API | today's bars for `SYMBOL.NS`, `range=1d&interval=5m` (or `1m`): free, unofficial, can lag |
| `trader/entry.json` | with `check --write`, or when `watch` triggers: symbol, setup, status, time, bar, price, level, opening range |

## The rule

- **Opening range (orb).** The high and low of the first 15 minutes: the
  9:15, 9:20 and 9:25 five-minute bars, or fifteen 1-minute bars. The level
  to beat is the range high.
- **Level.** A price you give, like a 20-day high from `/trader-scanner`.
- **The trigger** is the first completed bar after the range that CLOSES
  above the level. A wick above is not a trigger. A close exactly at the
  level is not above it.
- **The time** is that bar's close time (the 10:10 bar closes at 10:15 AM IST).
  The price is its close, on the Rs 0.05 tick.
- **Only closed bars count.** A bar is closed when the clock passes its start
  plus 5 (or 1) minutes and Yahoo has caught up to that moment (it waits a
  minute at most). Yahoo's live tick, like 10:49:45, is never a bar.
- **Volume, if you want it.** `--min-volume-x 1.5` also needs the trigger
  bar's volume at 1.5 times the range bars' average. The 9:15 bar holds the
  opening auction, so 1.0 is already strict.
- **Time limits.** No entries before the range is done (9:30; the first
  completed bar closes at 9:35) or after 15:00 (config). Brokers square off
  intraday positions around 3:15 to 3:25 PM, so 15:00 leaves room to get out.
  The session is 9:15 AM to 3:30 PM IST: 75 five-minute bars, the last one
  starting at 3:25 PM.
- **What it says.** Waiting (and how far the last close is from the level),
  triggered, expired, or no data. Before 9:15: not open yet. Before 9:30: the
  range is still forming. Weekends and NSE holidays (the 2026 list is built
  in; special Saturday or Muhurat sessions are not): the market is closed.
  Dates outside 2026 are treated as ordinary weekdays.

## Steps

1. Get the symbol from the user, or run `entry.py watchlist` after
   `/trader-scanner`. Check `/trader-news` for it first.
2. Run `entry.py check SYMBOL`. Tell the user the status in one line:
   waiting and how far, triggered at what time and price, or expired.
3. To wait for it, Claude can run `entry.py watch SYMBOL --until 15:00` in
   the background, or `entry.py check SYMBOL --write` on a `/loop` every 5
   minutes. `watch` wakes just after each bar closes, prints one line per
   bar, and exits 0 on the trigger (it writes `trader/entry.json`) or 1 when
   the setup expires. Keep the computer awake while it watches: a sleeping
   laptop pauses it, and it catches up, late, when it wakes.
4. When it triggers, say the time and the price, and that nothing was placed.
   If the trigger is more than a bar old, say that too: a late entry is a
   different trade.
5. Hand off to `/trader-exit` to set the stop and the target BEFORE anything
   is bought.

## Example (illustrative: invented numbers, not real data)

RELIANCE, a Monday, 5-minute bars. The opening range (9:15 to 9:30) is
Rs 1,268.40 to Rs 1,275.60. At 10:12 the 10:10 bar is still open, so it waits:

```
WAITING  last close Rs 1,274.90 (10:05 bar), Rs 0.70 under the range high Rs 1,275.60 (-0.05%).
The 10:10 bar is still forming (Rs 1,277.30 so far, closes 10:15 AM IST); it does not count until it closes.
```

At 10:15 the bar has closed:

```
RELIANCE  Mon 2026-11-16 10:15 IST  opening-range breakout (15-minute range) on 5-minute bars (Yahoo, free, can lag)
Opening range 9:15-9:30: high Rs 1,275.60, low Rs 1,268.40 (3 of 3 bars).
TRIGGERED 10:15 AM IST at Rs 1,277.30: the 10:10 bar (bar 11) closed above the range high Rs 1,275.60 (+0.13%).
This is the moment to get in, if you take the trade. Nothing was placed.
Next: set the stop and target BEFORE you buy: /trader-exit (exit.py plan --from trader/entry.json).
```

With `--min-volume-x 1` a thin trigger bar would be skipped and the trigger
would move to the next close above the range high that also has the volume.

## Rules

- Bar by bar, on free Yahoo 1-minute or 5-minute bars. They are unofficial
  and can lag. Say so when a minute matters.
- A signal is information, not an order, and not a promise. Nothing here
  promises winning trades or money.
- Long side only. Long side only in this pack. If the user wants a short, say that.
- One trigger per setup per day: the first close above. Later closes do not
  reset it.
- Never call an entry early because a bar looks like it will close above.

## What it never does

It never places an order, never sizes a position, never sets the stop (that
is `/trader-exit`), never moves the level after the fact, and never counts a
bar that has not closed. It never runs `/trader-broker` from a background
watch: nobody is there to say yes.

## Safety

- Education and tooling, not investment advice, and not a SEBI-registered research or advisory service.
  A PASS is a rules check, not a recommendation.
- Nothing in this pack can place an order. trader-broker only prepares a ticket that the user places by
  hand in their own broker's app, after trader-risk passed that exact order today. There is no broker
  connection and no broker keys anywhere. trader-entry only reads Yahoo bars and writes trader/entry.json.
- Intraday equity only, long side only. No futures, options, short selling or leverage unless the config
  allows it and the user confirms.
- Brokerage, STT, exchange charges, GST and stamp duty come off every trade, and intraday equity profits
  are taxed in India as business income: tax and costs are the user's to check with a chartered
  accountant.
