---
name: trader-budget
description: >-
  Budget Manager (India: NSE intraday, rupees). Sizes every position to your
  budget and your max loss per trade. Reads the trade plan from trader-exit
  (entry, stop, target), finds the whole shares that fit inside four limits
  (max loss per trade, position cap, max order, cash after your buffer), says
  which limit decided it, and writes ONE proposed order (entry, stop-loss,
  target, marked NSE and MIS intraday) to trader/orders.json. A stop too far
  away for your max loss is a plain refusal, not a smaller order. Nothing is
  placed. Use when the user says "how many shares", "size this trade", "how
  much should I buy", "I have Rs 1,00,000", "I only want to risk Rs 500 a
  trade", "set my rules", "keep 10% in cash", or after /trader-exit writes a
  plan.
argument-hint: "[budget in rupees]"
---

# trader-budget

The Budget Manager turns a plan ("buy RELIANCE at 1271.40, stop 1265.70") into
an exact order ("buy 58 shares"), inside rules the user sets once. The stop
decides the size: the further away the stop, the fewer shares. It writes a
proposal only. trader-risk checks it and trader-broker prints a ticket that the
user places by hand in their own broker's app. Day trading loses most people
money. Sizing to a max loss keeps each loss small; it does not make a trade win.

All times are Indian Standard Time (IST). All money is in rupees, written
"Rs 1,271.40". Prices sit on the NSE tick of Rs 0.05. Whole shares only.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py"                        # trader/plan.json + trader/config.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --write                # write trader/orders.json
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit --write        # a limit order at the plan's entry
python3 "${CLAUDE_SKILL_DIR}/size.py" --limit 1271.00 --json  # a limit order at 1271.00
python3 "${CLAUDE_SKILL_DIR}/size.py" --weights TCS=40,INFY=60 --config split.json   # weights mode, below
```

On Windows use `python` or `py` instead of `python3`.

`--now "2026-11-16 10:00"` pins the clock (IST). A plan for another day is
refused: make a new one with trader-exit.

## What it reads and writes

| file | what |
| --- | --- |
| `trader/config.json` | the rules (start from `config.example.json` in this folder) |
| `trader/plan.json` | the trade: entry, stop, target, setup, flat-by time (trader-exit writes it) |
| `trader/prices.json` | optional: a fresh price above the plan's entry means a bigger risk (trader-alerts writes it) |
| `trader/portfolio.json` | optional: its cash caps the size (trader-broker keeps it) |
| `trader/orders.json` | the one proposed order it writes with `--write` |

## Step 1: set the rules once

If `trader/config.json` does not exist, copy `config.example.json` into
`trader/config.json` and ask the user for each value in plain words:

- **budget**: how much money this is for, in rupees. Only money they can afford to lose.
- **cash_buffer_pct**: how much always stays in cash (default 10).
- **max_loss_per_trade_usd**: the most one trade may lose if the stop fills at the stop.
  The example file has Rs 500 on a Rs 1,00,000 budget.
- **max_position_pct**, **max_order_usd**, **min_order_usd**: the biggest position (75% of the
  budget), the biggest order (Rs 75,000) and the smallest order (Rs 500).
- The day limits trader-risk enforces: **max_daily_loss_usd** (Rs 1,500), **max_trades_per_day** (3),
  **min_reward_risk** (1.0), **require_stop** (true), **no_entries_before** / **no_entries_after**
  ("09:35" / "15:00") and **flat_by** ("15:10"), all IST.
- **blocked**: symbols they never want to trade.

The key names keep the old `_usd` ending so the pack's files still fit together.
In this India edition every one of those amounts is in rupees. Say so when you
read the file back to the user.

Why 15:10 and not 15:30: brokers close intraday (MIS) positions on their own
around 3:15 to 3:25 PM, at a price the user does not choose. Being flat by 3:10
PM is the user's own exit.

## Step 2: size the trade

```bash
python3 "${CLAUDE_SKILL_DIR}/size.py" --write
```

Whole shares only. The size is the smallest of four limits:

| limit | shares |
| --- | --- |
| max loss | `max_loss_per_trade_usd` / risk a share (entry minus stop) |
| position cap | budget x `max_position_pct` / entry |
| max order | `max_order_usd` / entry |
| cash | (budget minus the cash buffer) / entry, never more than the cash in `trader/portfolio.json` |

The entry it sizes at: the limit price with `--limit`. For a market order, the
plan's entry, or the price in `trader/prices.json` if it is fresh (under 15
minutes old) and higher. A price that ran up since the plan means a bigger
loss at the same stop, so fewer shares. A lower price never shrinks the risk.

It refuses, and writes no order, when: the size is zero shares, the order is
under the minimum, reward:risk is under `min_reward_risk`, the stop is not
below the entry, the target is not above it (the move already happened), the
plan is for another day, the symbol is blocked, or the plan is a short. Say
the reason to the user in one line.

## Step 3: show the user

Show the four limits, which one decided the size, the shares, the rupees
and the max loss at the stop. Say plainly that a stop is an order, not a
promise: in a fast market it can fill below the stop. Say too that brokerage,
STT, exchange charges, GST and stamp duty come off every trade and are not in
the max loss figure. Then hand over to `/trader-risk`.

## Example (illustrative: invented numbers, not real data)

RELIANCE on a made-up trading day. Opening-range breakout: entry 1271.40,
stop 1265.70, target 1282.80 (2R). Risk 5.70 a share. The example config:
Rs 1,00,000 budget, 10% cash buffer, Rs 500 max loss.

| limit | the math | shares |
| --- | --- | --- |
| max loss | Rs 500 / 5.70 | 87 |
| position cap | 75% of Rs 100,000 = Rs 75,000 / 1271.40 | **58 (decides it)** |
| max order | Rs 75,000 / 1271.40 | 58 |
| cash | Rs 100,000 minus Rs 10,000 = Rs 90,000 / 1271.40 | 70 |

58 shares = Rs 73,741.20. Max loss at the stop: 58 x 5.70 = Rs 330.60. It writes:

```json
{"symbol": "RELIANCE", "exchange": "NSE", "product": "MIS", "side": "buy", "qty": "58",
 "type": "market", "time_in_force": "day", "order_class": "bracket",
 "take_profit_limit_price": "1282.80", "stop_loss_stop_price": "1265.70",
 "why": "day trade on RELIANCE: 58 shares, bound by your position cap (58 x 5.70 = Rs 330.60 at the stop)",
 "plan": {"entry": 1271.4, "stop": 1265.7, "target": 1282.8, "risk_per_share": 5.7,
          "max_loss": 330.6, "flat_by": "15:10"}}
```

`why` and `plan` are notes for trader-risk and trader-broker. The file keeps one
bracket-shaped record so the three legs stay together; trader-broker shows it
to the user as THREE separate orders to place by hand, because many Indian
brokers no longer offer bracket orders. With the stop at 1200.00 instead, one
share would risk 71.40, so the max-loss limit gives Rs 500 / 71.40 = 7 shares
and now decides the size. But the target at 1282.80 would then be worth only
0.16 of that risk, under the minimum reward:risk of 1.0, so the order is
refused unless the target moves too. A stop so far away that even one share
risks more than the max loss (above Rs 500 here) gives no order.

## Weights mode (kept from v1)

`--weights TCS=22.04,INFY=10.86` or `--targets FILE` (`targets.example.json`
here) splits a budget across a list by weight: the cash buffer comes off the
top, weights are renormalised to 100, any stock over `max_position_pct` is
pinned at the cap and its excess shared out, slices under the minimum order
are dropped, and amounts round to whole rupees so nothing is left idle by
accident. It buys whole shares and needs prices (`--prices trader/prices.json`).
These are plain buys with no stop: trader-risk blocks them while
`require_stop` is true and counts each one against `max_trades_per_day`. Use
a separate config (`--config`) for a long-term split. Note that the rest of this
pack is intraday only: a long-term split would be delivery (CNC), which
trader-risk does not allow.

## Rules

- Proposals only. This skill never contacts a broker.
- Never size money the user has not said is for this. Ask for the budget and the max loss.
- Every number comes from the config, the plan or the prices. Nothing is guessed.
- No projections: never say what a trade will make. A target is a plan, not a forecast.
- Free Yahoo prices are unofficial, delayed and can lag. The broker's price is the one that fills.

## What it never does

It never places, approves or schedules an order, never raises a limit on its
own, never shrinks a stop to fit more shares, and never sizes options,
margin or short positions.

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
