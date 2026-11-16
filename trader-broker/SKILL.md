---
name: trader-broker
description: >-
  Order Ticket (India: NSE intraday, IST, rupees). Turns a risk-checked order
  into a plain ticket you place by hand in your own broker's app, and keeps the
  books. Nothing is ever sent to a broker: there is no broker connection, no
  API and no keys. Shows each order as THREE orders to place (the BUY, the
  stop-loss SELL and the target SELL, since many Indian brokers no longer offer
  bracket orders) with the max loss at the stop, records your yes word for word
  so one yes covers one ticket, builds the SELL ticket that closes a day trade
  by your flat-by time, records what you placed and what filled, and logs each
  trade's max loss so trader-risk can hold the daily limit. Use when the user
  says "show me the ticket", "what do I place", "I'll buy it", "I placed it",
  "close my position", "flatten", "get me out", "log my fill", or after
  /trader-risk passes.
argument-hint: "[order number]"
---

# trader-broker

The Order Ticket is the last step before the user acts. It never places an
order and it cannot: it has no connection to any broker. It prepares a ticket
in plain words and the user places the orders themselves in their own broker's
app (the mobile app or web terminal). A ticket is shown as READY only after:

1. **trader-risk passed this exact order today** (matched by fingerprint), and
2. **the user typed an explicit yes for this one ticket** in the chat, saying
   they saw it and will place it themselves.

No PASS, no ticket. No yes, no ticket marked approved. The user is always the
one pressing the button at their broker.

All times are Indian Standard Time (IST). All money is in rupees. Intraday
(MIS) equity on the NSE, long side only.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show                     # every ticket, READY or not
python3 "${CLAUDE_SKILL_DIR}/ticket.py" approve --index 1 --reply "yes"
python3 "${CLAUDE_SKILL_DIR}/ticket.py" decline --index 1 --reply "no"
python3 "${CLAUDE_SKILL_DIR}/ticket.py" result --index 1 --status placed --filled-qty 58 --filled-price 1271.40
python3 "${CLAUDE_SKILL_DIR}/ticket.py" fill --symbol RELIANCE --side sell --qty 58 --price 1282.80
python3 "${CLAUDE_SKILL_DIR}/ticket.py" flatten --symbol RELIANCE --qty 58
python3 "${CLAUDE_SKILL_DIR}/ticket.py" log
```

On Windows use `python` or `py` instead of `python3`.

`ticket.py` renders tickets, checks that a reply is a real yes for that order,
builds the flatten ticket, and keeps the log in `trader/state/broker.json`.
`--now "2026-11-16 10:00"` pins the clock (IST).

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the proposed orders (trader-budget writes it; `flatten` replaces it) |
| `trader/state/risk.json` | trader-risk's verdicts; only a PASS from today is READY |
| `trader/state/broker.json` | every yes, no, placed, failed and filled, with each entry's max loss |
| `trader/portfolio.json` | cash and shares, updated by `fill` and by `result --filled-qty` |
| `trader/plan.json` | the flat-by time for `flatten` |

## What the ticket says

An entry is one bracket-shaped record in `trader/orders.json`, but the ticket
shows it as THREE orders for the user to place by hand:

1. **BUY** qty SYMBOL, NSE, MIS (intraday), market or limit, good for today.
2. **SELL stop-loss**, trigger at the stop price.
3. **SELL target**, limit at the target price.

Many Indian brokers no longer offer bracket orders, so the stop-loss and the
target are two separate orders. When one fills, the user must cancel the other
by hand, or it can fill later and open an unwanted short position. Which order
types exist (stop-loss limit SL, stop-loss market SL-M, limit) differs by
broker: tell the user to check their own broker's app. Do not name features of
a specific broker; this pack does not know them.

Place the BUY first. The stop-loss and the target can be placed once the BUY
has filled, because a SELL of shares the user does not yet hold is a short sale.

## Steps: the entry

1. `ticket.py show`. Only READY tickets go to the user. A ticket that is NOT
   READY or BLOCKED goes back to `/trader-risk`. A verdict from an earlier day
   is not READY.
2. Show ONE ticket and ask: "You will place this by hand. Reply yes or no."
   One order per question. Never offer "yes to all".
3. Run `ticket.py approve --index N --reply "<the user's reply, word for word>"`.
   If it prints "Not recorded", the reply was not an explicit yes for this
   order (for example "sure", "yes to all", or a yes that names a different
   stock or amount). Ask again. Never turn a reply into a yes yourself.
4. After "Recorded your yes", tell the user to place the three orders in their
   broker's app. Nothing is sent from here.
5. When they say what happened, record it: `ticket.py result --index N
   --status placed --filled-qty Q --filled-price P` (the fill price they read
   in their broker's app), or `--status skipped`, or `--status failed` with
   `--note`. A failed order is not retried without a new check and a new yes.
   The log keeps the entry's max loss for trader-risk's daily limit.

## Steps: while it is open, and out by the close

- trader-alerts watches the stop, the target and the flat-by time
  (`alerts.py add --from-plan`). The stop-loss and target orders at the broker
  do the stopping; the alerts only tell the user.
- When the stop-loss or the target fills, the user cancels the other order,
  then record it: `ticket.py fill --symbol RELIANCE --side sell --qty 58
  --price 1265.70`.
- By `flat_by` (15:10 IST), anything still open gets closed. Brokers square off
  MIS positions on their own around 3:15 to 3:25 PM at a price the user does not
  choose, so 3:10 is the user's own exit:
  1. The user reads how many shares they hold in their broker's positions
     screen. (Run `ticket.py fill` first if the buy is not recorded yet.)
  2. `ticket.py flatten --symbol RELIANCE --qty 58` writes a market SELL (MIS)
     ticket for those shares to `trader/orders.json`.
  3. `/trader-risk`. A sell that only closes what the user holds is never
     blocked by the daily limits or the entry window.
  4. `ticket.py show`, then the user's yes for that one ticket, as above.
  5. The stop-loss and target orders still hold those shares, and many brokers
     refuse a new sell while they do. The user cancels both in their broker's
     app, then places the SELL, then `ticket.py result`.

## Example (illustrative: invented numbers, not real data)

```
ORDER 1 of 1, NSE intraday (MIS), long only. Nothing is sent anywhere: you place it by hand.
  Place these THREE orders in your own broker's app:
  1. BUY 58 RELIANCE NSE, MIS (intraday), market order (the plan's entry is about Rs 1,271.40; a limit order near it is safer), good for today
  2. SELL stop-loss, trigger at Rs 1,265.70 (58 shares of RELIANCE, NSE, MIS)
  3. SELL target, limit at Rs 1,282.80 (58 shares of RELIANCE, NSE, MIS)
  max loss about Rs 330.60 if the stop fills at Rs 1,265.70 (it can fill worse in a fast market)
  why: day trade on RELIANCE: 58 shares, bound by your position cap (58 x 5.70 = Rs 330.60 at the stop)
  READY: trader-risk PASS, waiting for your yes
  Many Indian brokers no longer offer bracket orders, so the stop-loss and the target are two separate orders: when one fills, cancel the other yourself. Check which order types (SL / SL-M, limit) your broker offers.
```

The user replies "yes". Claude records it with `approve`. The user then places
the three orders in their broker's app, and tells Claude the fill so `result`
can record it. The `why` and the plan stay in the file.

## What it never does

- Never places, sends, routes or schedules an order. It has no connection to any broker.
- Never marks a ticket approved without an explicit yes for that one ticket, and never covers two
  tickets with one yes.
- Never asks for, reads, stores or repeats broker logins, API keys, passwords or OTPs. If the user
  pastes one, tell them to change it.
- Never prepares an order from a scheduled or background task: nobody is there to say yes.
- Never promises a fill price: a market order and a stop fill at whatever the market gives.

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
