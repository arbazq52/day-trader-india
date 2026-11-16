---
name: trader-risk
description: >-
  Risk Manager (India: NSE intraday, IST, rupees). Checks every trade against
  your limits and stops anything over them, before a ticket is shown. For a
  day trade: a stop is required, the loss at the stop must fit your max loss
  per trade (measured from the higher of the plan's entry and a fresh price),
  reward:risk must meet your minimum, the day's total risk must fit your daily
  loss limit, no more than your trades per day, and no new entries outside
  your entry window or when the NSE is closed. It also keeps the basics:
  blocked symbols, order size, position cap, cash buffer, margin, short sales,
  options, anything that is not NSE equity bought intraday (MIS), prices off
  the Rs 0.05 tick, malformed orders, duplicates and a daily order limit.
  Getting out is never blocked by a day limit. Prints PASS or BLOCK with the
  reason and records the verdicts so trader-broker only shows a ticket that
  passed. Use when the user says "check my order", "is this safe", "risk
  check", "does this break my rules", "can I take this trade", "how much have
  I risked today", or before /trader-broker, always.
argument-hint: "[path to orders.json]"
---

# trader-risk

The Risk Manager is the gate between a proposal and a ticket. Every order
written by trader-budget or trader-broker's flatten passes through it. A
BLOCK is final for that order: it does not go to the user for a yes and no
ticket is shown. Most people who day trade lose money. These limits keep each
loss and each day's losses small. They do not make a trade win.

All times are Indian Standard Time (IST), worked out in the tool, never from
the computer's clock zone. All money is in rupees.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py"                           # trader/ files; writes trader/state/risk.json
python3 "${CLAUDE_SKILL_DIR}/check.py" --json
python3 "${CLAUDE_SKILL_DIR}/check.py" --no-write                # look without recording
python3 "${CLAUDE_SKILL_DIR}/check.py" --now "2026-11-16 10:00"  # pin the clock (IST)
```

On Windows use `python` or `py` instead of `python3`.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/orders.json` | the proposed orders (trader-budget, or trader-broker's flatten) |
| `trader/config.json` | the limits (trader-budget ships `config.example.json`) |
| `trader/portfolio.json` | cash and holdings; if missing, a fresh account funded with the budget |
| `trader/prices.json` | a fresh price raises the entry it measures risk from; also values holdings |
| `trader/state/broker.json` | what was placed today: duplicates, trades per day, daily loss |
| `trader/state/risk.json` | the verdicts it writes, with a fingerprint of each exact order |

## Entries and exits

An **entry** opens or adds to a position: a buy, or a sell that would go
short. An **exit** only reduces what you already hold. Getting out must
always be possible, so an exit is checked for format, venue and short sales
only. Every other rule (day limits, entry window, loss, reward:risk, blocked
list, size, duplicates) turns into a warning for an exit, never a BLOCK. To
record that you hold a position, run `ticket.py fill` in trader-broker first:
a sell of shares the tool does not know you hold is blocked as a short.

## The checks

Orders are checked in file order, as if each passed order had filled, so a
batch that is fine order by order but breaks a limit together is caught.

| check | blocks when |
| --- | --- |
| format | no symbol, side not buy or sell, no whole-share qty, a limit order with no limit price; a bracket-shaped order that is not whole shares, not `day`, or misses its stop-loss or take-profit |
| venue | the exchange is not NSE or the product is not MIS (intraday). Delivery (CNC), carry-forward (NRML) and margin products are not allowed |
| tick | a price that is not a multiple of Rs 0.05 |
| asset | not a plain NSE stock symbol; futures and options while `allow_options` is false |
| short | a sell of more than you hold (`allow_short` false) |
| blocked | (entries) the symbol is on the `blocked` list |
| size | (entries) under `min_order_usd` or over `max_order_usd` |
| position | (entries) the stock would be over `max_position_pct` of the account |
| cash | (entries) the buy would leave less than the cash buffer, or need margin |
| stop | (entries) no stop while `require_stop` is true (a bracket `stop_loss_stop_price`, or the order's plan stop); a stop on the wrong side of the entry |
| loss | (entries) qty x (entry minus stop) over `max_loss_per_trade_usd` |
| reward:risk | (entries) (target minus entry) / (entry minus stop) under `min_reward_risk` |
| daily loss | (entries) the max losses at the stops of today's entries, plus this one, over `max_daily_loss_usd` |
| trades | (entries) `max_trades_per_day` entries already placed today |
| window | (entries) before `no_entries_before` or after `no_entries_after`, or the NSE is closed |
| duplicate | (entries) the same symbol and side twice in one batch, or already placed today |
| daily limit | (entries) `max_orders_per_day` orders already placed today |

The `_usd` ending on the config keys is kept so the pack's files fit together.
In this edition those amounts are rupees.

How the numbers work:

- **The entry it measures from**: the limit price for a limit order. For a
  market order, the HIGHER of the plan's entry and a fresh price from
  `trader/prices.json` (under 15 minutes old). A plan written at 10:00 cannot
  understate the risk at 10:40 after the price ran up. An older price is not
  used, and it says so.
- **Daily loss** counts the full max loss of every entry placed today, win or
  lose, as trader-broker logged it. Three full-size trades use up a Rs 1,500 day.
- **The window** is IST. The market is open 9:15 AM to 3:30 PM, Monday to
  Friday, except NSE holidays. The default entry window is 9:35 AM (the first
  completed bar after the opening range) to 3:00 PM. Set both `no_entries_*`
  to null to switch the window off.
- **The holiday list** covers 2026 only. For any other year the tool treats
  every weekday as open and warns: check nseindia.com for that year's
  holidays. It does not know about special weekend sessions (a Budget-day
  Saturday, Muhurat trading).
- **MIS is intraday**: brokers square off open MIS positions on their own
  around 3:15 to 3:25 PM. `flat_by` defaults to 15:10 so the exit is the user's
  choice, not the broker's.

Warnings do not block, but say them to the user: a price too old to use, a
stop that lives only in the plan and not on the order, a bracket stop that
differs from the plan's, a year the holiday list does not cover. (trader-exit
separately warns when `flat_by` is 3:15 PM or later.)

## Steps

1. If the price may have moved since the plan, refresh it first
   (trader-alerts: `alerts.py quote RELIANCE --write`).
2. Run `check.py`. Exit code 0 means every order passed, 1 means at least one
   was blocked.
3. Tell the user the result in plain words, order by order: the max loss at
   the stop, reward:risk, and how much of today's limits it uses. For a
   BLOCK, give the reason and the fix (fewer shares, a closer stop from
   trader-exit, wait for the window, or skip the trade). Never change a
   limit yourself.
4. If the order changes in any way, run the check again. trader-broker matches
   each order to its verdict by fingerprint, so an edited order is not ready
   until it passes again, and a verdict from yesterday does not count today.

## Example (illustrative: invented numbers, not real data)

The RELIANCE order from trader-budget at 10:01 AM IST on a made-up trading day,
on a fresh Rs 1,00,000 account with the example config:

```
PASS  #1 buy RELIANCE 58 shares, entry
          entry 1271.40 (the plan's entry), stop 1265.70, target 1282.80: risk 5.70 a share
          max loss Rs 330.60 (limit Rs 500), reward:risk 2.00 (min 1)
          today before this: 0 of 3 trades, Rs 0 of Rs 1,500 daily loss

1 passed, 0 blocked at 2026-11-13 10:01 IST. Cash after the passed orders: Rs 26,258.80.
```

Too many shares, and it is blocked:

```
BLOCK #1 buy RELIANCE 88 shares, entry
          entry 1271.40 (the plan's entry), stop 1265.70, target 1282.80: risk 5.70 a share
          max loss Rs 501.60 (limit Rs 500), reward:risk 2.00 (min 1)
        - size: Rs 111,883.20 is over your Rs 75,000 max order
        - cash: needs Rs 111,883.20 but only Rs 100,000 cash; that would be margin (borrowed money)
        - position: RELIANCE would be Rs 111,883.20, 111.9% of the Rs 100,000 account, over your 75% cap
        - loss: 88 shares x 5.70 risk a share = Rs 501.60 at the stop, over your Rs 500 max loss per trade
```

The same 58 shares with product CNC (delivery) are blocked by the venue check,
and at 9:20 AM they are blocked by the window (no new entries before 09:35). A
SELL that closes shares you hold at 3:10 PM passes even though it is after the
3:00 PM entry cutoff: it is an exit.

## Rules

- A PASS only means the order is allowed to be shown to the user. It is not a yes.
- Every number comes from the config, the order, the portfolio, the prices or the broker log.
- Free Yahoo prices are unofficial and delayed; the broker's price is the one that fills, and a
  stop can fill worse than its price in a fast market.

## What it never does

It never places an order, never edits an order to make it pass, never
loosens a limit, never blocks a sell that only gets the user out, and never
treats a PASS as the user's yes.

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
