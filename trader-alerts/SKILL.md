---
name: trader-alerts
description: >-
  Price Alerts. Rings when a price, a stop or the opening bell hits. Turns
  the trade plan into three alerts in one go (the stop, the target and "flat
  by close" at your flat-by time, 3:10 PM IST by default), plus above / below
  / stop / target levels, percent moves from the previous close, any time of
  day, and the NSE opening bell at 9:15 AM IST, each ringing once so you are
  not spammed. Knows NSE hours (9:15 AM to 3:30 PM IST) and the 2026 NSE
  trading holidays, works out IST itself, fetches free delayed quotes (Yahoo
  chart JSON, SYMBOL.NS) one ticker at a time, shows prices in rupees, and
  writes trader/prices.json for sizing and the risk check. Use when the user
  says "alert me when", "tell me if RELIANCE hits", "watch my stop", "watch
  my trade", "remind me to close by 3:10", "is the market open", "when does
  the market open", "get me a price", or right after /trader-exit writes a
  plan.
argument-hint: "[symbol] [price]"
---

# trader-alerts

Price Alerts watches the numbers so the user does not have to stare at a
chart. An alert is information, never an order: when a stop alert rings,
nothing is sold by this skill. The stop-loss and the target are orders the
user placed by hand in their own broker's app and they do the work; the
alerts tell the user what happened and when it is time to be flat.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/alerts.py" clock                          # NSE open or closed, next open
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --from-plan                # stop, target, flat by close from trader/plan.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --opening-bell
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --stop 1262.40
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol RELIANCE --target 1284.40
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --at 15:10 --label "flat by close"
python3 "${CLAUDE_SKILL_DIR}/alerts.py" add --symbol INFY --pct 3
python3 "${CLAUDE_SKILL_DIR}/alerts.py" check                          # exit 0 = something rang
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote RELIANCE --write         # -> trader/prices.json
python3 "${CLAUDE_SKILL_DIR}/alerts.py" quote --holdings --write       # portfolio + plan symbols
python3 "${CLAUDE_SKILL_DIR}/alerts.py" list
python3 "${CLAUDE_SKILL_DIR}/alerts.py" reset reliance-plan-stop
```

`--now "2026-11-16 15:10"` pins the clock (IST; add `Z` for UTC);
`--offline DIR` reads saved quote files (`yahoo-<SYMBOL>.json`) instead of
the network.

Symbols are plain NSE symbols: `RELIANCE`, `M&M`, `BAJAJ-AUTO`. The tool sends
Yahoo `SYMBOL.NS` (URL-quoted, so `M&M` goes out as `M%26M.NS`) and strips the
`.NS` from whatever comes back. Prices are in rupees ("Rs 1,284.40").

## What it reads and writes

| file | what |
| --- | --- |
| `trader/plan.json` | the trade from trader-exit, for `add --from-plan` |
| `trader/alerts.json` | the rules (`alerts.example.json` in this folder) |
| `trader/state/alerts.json` | which rules rang and when, so each rings once |
| `trader/prices.json` | the latest quotes, merged in, for trader-budget and trader-risk |
| `trader/portfolio.json` | the symbols held, for `quote --holdings` |
| `trader/config.json` | `flat_by` when the plan has none (default 15:10 IST) |

## Rule types

| type | rings when | rings again |
| --- | --- | --- |
| `above` / `target` | price at or above `price` | after `reset`, or on its own if `"rearm": true` and the price fell back |
| `below` / `stop` | price at or below `price` | same |
| `pct_move` | moved `pct` percent from the previous close (or `ref`), optional `direction` up or down | once per day at most |
| `time` | the IST clock passed `at` ("15:10") on a trading day | once per trading day |
| `opening_bell` | the NSE is open (9:15 AM IST) | once per trading day |

A rule with `"date"` is watched on that IST date only; `--from-plan` rules
carry the plan's date, so yesterday's stop never rings today. Levels you type
and levels taken from a plan are put on the NSE tick, Rs 0.05 (nearest tick),
so 1262.43 becomes 1262.45 and the tool tells you. The NSE has no early
closes, so `before_close` in an old rule file changes nothing.

## Quotes

- `yahoo` (the only source): `query2.finance.yahoo.com/v8/finance/chart/<SYMBOL>.NS`,
  an unofficial free JSON endpoint, one request per symbol, half a second
  apart. On a 429 it waits and tries once more; on a 429 or a 5xx after that
  it tries `query1`. It identifies itself as `day-trader-skill/2.0`.
- Free quotes are unofficial, delayed and can lag. They are fine for alerts
  and for checking a size, not for timing an order. The price in the user's
  broker app is the one that fills. Each price in `trader/prices.json` keeps
  its quote time, and trader-risk only uses one under 15 minutes old.
- If Yahoo is down, ask the user to read the price off their broker app and
  write it into `trader/prices.json` as
  `{"as_of": "...Z", "prices": {"RELIANCE": 1274.55}}`.

## The NSE clock

Regular session 9:15 AM to 3:30 PM IST, Monday to Friday. IST is UTC+5:30 all
year with no daylight saving; the tool works it out itself and ignores the
computer's own time zone. Closed on weekends and on these 2026 NSE trading
holidays (a copy of the exchange's list: confirm at nseindia.com):

- Jan 15 (Maharashtra Municipal Corporation Election), Jan 26 (Republic Day),
  Mar 3 (Holi), Mar 26 (Shri Ram Navami), Mar 31 (Shri Mahavir Jayanti),
  Apr 3 (Good Friday), Apr 14 (Dr. Baba Saheb Ambedkar Jayanti), May 1
  (Maharashtra Day), May 28 (Bakri Id), Jun 26 (Muharram), Sep 14 (Ganesh
  Chaturthi), Oct 2 (Mahatma Gandhi Jayanti), Oct 20 (Dussehra), Nov 10
  (Diwali-Balipratipada), Nov 24 (Prakash Gurpurb Sri Guru Nanak Dev),
  Dec 25 (Christmas).
- No early closes. The special Diwali Muhurat evening session and any special
  Saturday sessions are not in the list: the tool treats them as closed.
- For any year other than 2026 the tool treats weekdays as ordinary trading
  days and says the holiday list is unknown.

## Steps

1. Right after trader-exit writes the plan, run `add --from-plan`. Confirm
   the three alerts back to the user: the stop, the target and the flat-by
   time (3:10 PM IST by default, because many brokers square off intraday
   positions on their own around 3:15 to 3:25 PM).
2. Run `check` while the trade is open: every few minutes from a Claude
   scheduled task or `/loop`. Each run fetches only the symbols in today's
   rules and rings each alert once. A check reads the latest delayed quote;
   it is not a live feed, and a price can pass a level between two checks.
3. Tell the user what rang in one line each. A stop or target alert means the
   matching order in their broker app has probably filled: they check there,
   cancel the other order (the stop-loss and the target are two separate
   orders) and record the fill with trader-broker. "Flat by close" means
   close anything still open by hand: `ticket.py flatten` in trader-broker
   prepares the sell ticket, then trader-risk. Never act for them.

## Example: the reel (illustrative: invented numbers, not real data)

RELIANCE on Monday 2026-11-16: entry Rs 1,274.55 at 10:15 AM, stop
Rs 1,262.40, target Rs 1,298.85, flat by 15:10. `add --from-plan` writes
`reliance-plan-stop`, `reliance-plan-target` and `reliance-flat-by` for that
day. A `check` at 10:53 reads an invented quote, Rs 1,279.30, between the stop
and the target:

```
NSE OPEN (2026-11-16 10:53 IST, regular session).
Nothing hit. 3 rule(s) watched today, RELIANCE Rs 1,279.30.
```

At 3:10 PM:

```
ALERT Flat by close: it is 15:10 IST (set for 15:10), the market closes at 15:30. If RELIANCE is still
open, close it by hand in your broker's app: ticket.py flatten --symbol RELIANCE (trader-broker) prepares
the sell ticket. Many brokers square off intraday positions on their own around 3:15 to 3:25 PM.
```

It rings once. The next morning the plan's three alerts are no longer
watched; with `add --opening-bell`, the bell rings at 9:15.

## Rules

- An alert is a fact about a price or the clock. Say it as a fact.
- Never present a quote as live. Free quotes are delayed and unofficial.
- Confirm every new rule back to the user: symbol, type, level, day.

## What it never does

It never places, cancels or changes an order, never claims a quote is
live, and never predicts where a price is going.

## Safety

- Education and tooling, not investment advice, and not a SEBI-registered research or advisory service.
  A PASS is a rules check, not a recommendation.
- Nothing in this pack can place an order. trader-broker only prepares a ticket that the user places by
  hand in their own broker's app, after trader-risk passed that exact order today. There is no broker
  connection and no broker keys anywhere.
- Intraday equity only, long side only. No futures, options, short selling or leverage unless the config
  allows it and the user confirms.
- Brokerage, STT, exchange charges, GST and stamp duty come off every trade, and intraday equity profits
  are taxed in India as business income: tax and costs are the user's to check with a chartered
  accountant.
