---
name: trader-scanner
description: >-
  Chart Scanner (India: NSE, IST). Scans thousands of NSE charts for setups:
  opening-range breakouts, flags, oversold bounces. Builds the list of
  NSE-listed EQ-series stocks from NSE's EQUITY_L.csv (or the Nifty 500), runs a
  pre-market scan of daily closes (20-day closing-high breakout, bull flag,
  reclaimed the 20-day average, oversold, oversold bounce) and an intraday
  opening-range breakout scan on 5-minute bars, then writes
  trader/watchlist.json for trader-news and trader-entry. Free Yahoo data
  (SYMBOL.NS), bar by bar. Use when the user says "scan the market", "find me
  setups", "what is breaking out", "opening range breakouts", "scan for bull
  flags", "oversold stocks", "pre-market scan", "build my watchlist", "what
  should I look at today", or at the start of a trading day before /trader-news.
---

# trader-scanner

The Chart Scanner is the first step of a day trade on the Indian market. It
reads thousands of free NSE charts and lists the ones that match a rule. That
is all it does. A scan is a list of charts that match a rule, not a list of
stocks to buy, and a setup on a chart is not a prediction. Most people who day
trade lose money; the scanner does not change that. It only saves you from
flipping through 2,000 charts by hand.

All times are Indian Standard Time (IST, UTC+5:30). The NSE cash session is
9:15 AM to 3:30 PM IST, Monday to Friday except exchange holidays. Prices are
in rupees.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/scan.py" universe                       # -> trader/universe.txt
python3 "${CLAUDE_SKILL_DIR}/scan.py" universe --source nifty500     # only the Nifty 500
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily                          # before the open -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily --symbols RELIANCE,TCS,INFY   # or --watchlist FILE, --limit 200
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb                            # after 9:35 AM IST -> trader/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb --at 10:00                 # cut the clock at 10:00 AM IST
python3 "${CLAUDE_SKILL_DIR}/scan.py" orb --watchlist trader/watchlist.json --json
```

On Windows use `python` or `py` instead of `python3`, and backslashes in paths.

Flags: `--min-price 50` and `--min-volume` (daily 500,000, orb 0),
`--or-minutes 15`, `--max-confirm 200` (orb stage 2),
`--now "2026-11-16 10:00"` (IST) to pin the clock, `--offline PATH`
to read saved Yahoo files, `--no-write`, `--show N`, `--json`. Exit code 0
when the scan found something, 1 when it found nothing or could not run (the
reason is one plain line).

## What it reads and writes

| file | what |
| --- | --- |
| `trader/universe.txt` | written by `universe`: one `SYMBOL\|Name` a line, read by `daily` and `orb` |
| `trader/watchlist.json` | written by `daily` and `orb`: `mode`, `as_of`, `universe`, `scanned`, `failed`, `hits[]`. trader-news and trader-entry read `hits[].symbol` |
| `trader/config.json` | read by `orb`: `no_entries_after` (default 15:00) |

Symbols in every file are plain NSE symbols (`RELIANCE`, `M&M`, `BAJAJ-AUTO`).
The scanner adds `.NS` only when it talks to Yahoo.

## The universe

`universe` downloads NSE's `EQUITY_L.csv` (every listed equity) and keeps a
row when:

1. Its series is EQ, the normal rolling-settlement equity series. Trade-to-trade
   (BE), SME and other series are out.
2. It is a plain symbol: letters, digits, `&` and `-`, up to 20 characters.
3. Its name does not say ETF, BeES, exchange traded, index fund or mutual fund
   (ETFs trade in the EQ series, so they are filtered by name).

`--source nifty500` reads the Nifty 500 constituents list instead: about 500
liquid names, which makes every scan much faster. If NSE's server refuses the
download, save the CSV from your browser (NSE's "securities available for
trading" page) and run `universe --offline PATH-TO.csv`.

## The daily scan (before the open)

Yahoo's spark endpoint returns closes for 20 symbols a request, so about 2,000
symbols take about 100 requests (a couple of minutes with the polite 0.3 s
pause). Liquidity comes from the spark meta: last price at least `--min-price`
(Rs 50) and last session's volume at least `--min-volume` (500,000 shares). Run
it before the open or after the close: during the session the volume is the
day's so far, and today's daily bar is left out until 3:30 PM IST.

The setups are computed from daily closes only (spark has no highs or lows):

| setup | the rule on closes |
| --- | --- |
| `breakout_20d` | the last close is above every close of the 20 sessions before it |
| `bull_flag` | up more than 10 % over the 10 sessions before the last 5, then the last 5 closes inside a 5 % range |
| `reclaim_ma20` | the close before was under its 20-day average, the last close is above it |
| `oversold` | RSI 14 (Wilder) under 30 |
| `oversold_bounce` | RSI 14 was under 30 yesterday and today closed up |

Hits are listed most traded first (price times volume).

## The opening-range breakout scan (during the session)

The opening range is the first `--or-minutes` (15) of the session: the 9:15,
9:20 and 9:25 five-minute bars. A hit is the first completed 5-minute bar to
CLOSE above the range high, at that bar's close time. The earliest possible hit
is the 9:30 bar closing at 9:35 AM, so run `orb` after 9:35 AM IST.

1. Stage 1, every symbol: spark closes of today's 5-minute bars, 20 a
   request. A chart goes on only if a completed bar after the range closed at
   or above the highest close of the range. That is a necessary condition
   (the range high is at least every range close), so no breakout is lost.
2. Stage 2, each candidate: the v8 chart with real highs and lows, one
   request each. Range high = the highest high of the range bars, range low =
   the lowest low. On a strong morning most charts are candidates, so stage 2
   checks at most `--max-confirm` (200) of them, the most traded first (price
   times volume so far), and prints PARTIAL with the count it skipped.
   `--max-confirm 0` checks them all.

For a fast answer, scan the Nifty 500, the daily watchlist or a list of names
you trade (`--watchlist`, `--symbols`).

A chart is usable only when every 5-minute bar from 9:15 to the cutoff is
there; a missing bar means a halt or a thin stock. Null closes are dropped,
a bar off the 5-minute grid (the live tick) is dropped, and a bar counts only
once it is complete (start + 5 minutes). Before 9:35 AM, on a weekend or an
NSE holiday, after the close, or after `no_entries_after` (an expired setup) it
prints one plain line and writes nothing.

## Data and limits

- Yahoo's chart and spark endpoints are free, unofficial and can lag. NSE data
  on Yahoo is delayed and bars are 5-minute bars, bar by bar, never tick by tick.
  query2 first, query1 on a 429 or 5xx, one retry after a 5-second wait on a 429.
- Partial results are said as partial: "Fetched 1,800 of 2,000 charts (200
  failed or had no data)". Never round a partial scan up to "the whole market".
- The calendar holds the 2026 NSE trading holidays. Weekend special sessions
  (a Budget-day Saturday, Muhurat trading) are not in it, and dates after 2026
  are treated as ordinary weekdays: say so if the user scans in 2027.

## Steps

1. Once a week or so: `scan.py universe` (or `--source nifty500`).
2. Before the open: `scan.py daily`. Tell the user the counts (fetched,
   liquid, scanned, hits) and the top few by setup.
3. After 9:35 AM IST (10:00 is a common time): `scan.py orb`. Tell the user how
   many usable charts broke their range and when, and that a later hit is
   closer to the price now.
4. The user picks one chart. Hand it on: `/trader-news SYMBOL` (what is moving
   it), then `/trader-entry SYMBOL` (the entry bar by bar). Never pick for them.

## Example (illustrative: invented numbers, not real data)

A scan at 10:00 AM IST on a trading day:

```
python3 scan.py orb --min-price 0
Fetched 1,812 of 1,830 charts (18 failed or had no data); 1,790 usable; 410 candidates, 200 confirmed with real highs and lows.
PARTIAL: 210 more candidates were not checked (only the 200 most traded are; --max-confirm 0 checks all).
37 of the 200 checked charts closed above their opening-range high by 10:00 AM:
   9:40 AM  RELIANCE      Rs 1,271.40  range 1,262.40 to 1,268.90  +0.20% over
  ...
```

RELIANCE's range is the 9:15 to 9:25 bars. The 9:35 bar closed at Rs 1,271.40,
0.20 % over the range high, at 9:40 AM. The user picks RELIANCE and Claude hands
it to `/trader-news RELIANCE`, then `/trader-entry RELIANCE`.

## Rules

- Say what was scanned: how many symbols, how many charts came back, how many
  were usable, and the time of the data (IST).
- Say "matched a rule", never "a buy", "a winner" or "a good trade".
- Never print a P&L, a return or a profit figure.
- A hit is stale once the price has moved on. Re-run before acting on it.

## What it never does

It never places, sizes or checks an order, never says which stock to buy,
never calls data real time, and never promises that a setup works.

## Safety

- Education and tooling, not investment advice, and not a SEBI-registered
  research or advisory service. A PASS is a rules check, not a recommendation.
- Nothing in this pack can place an order. trader-broker only prepares a ticket
  that the user places by hand in their own broker's app, after trader-risk
  passed that exact order today. There is no broker connection and no broker
  keys anywhere.
- Intraday equity only, long side only. No futures, options, short selling or
  leverage unless the config allows it and the user confirms.
- Brokerage, STT, exchange charges, GST and stamp duty come off every trade,
  and intraday equity profits are taxed in India as business income: tax and
  costs are the user's to check with a chartered accountant.
