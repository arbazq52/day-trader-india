# Day Trader skill pack, India edition (NSE, IST)

Nine Claude skills for intraday trading of NSE-listed stocks, in Indian
Standard Time and rupees. This is an India-only adaptation of the original
US pack: the scanner reads NSE's list of equities, every clock is IST, the
calendar is the NSE trading calendar, and nothing is ever sent to a broker.

> **Education and tooling, not investment advice.** This is not a SEBI-registered
> research or advisory service. Most people who day trade lose money; these
> tools do not change that. They only keep each loss small and save you from
> flipping through charts by hand. Brokerage, STT, exchange charges, GST and
> stamp duty come off every trade, and intraday profits are taxed in India as
> business income: check costs and tax with a chartered accountant.

Everything runs on free, unofficial, delayed data from Yahoo Finance
(`SYMBOL.NS`) plus NSE's published symbol list. Python 3.8+, standard library
only, nothing to install.

## The skills

| skill | what it does |
| --- | --- |
| `/trader-scanner` | Scans NSE charts for setups: opening-range breakouts, flags, oversold bounces. |
| `/trader-news` | New Yahoo Finance headlines for the stocks you watch, and how far each is from yesterday's close. |
| `/trader-entry` | Watches a setup bar by bar and says when the entry triggers. |
| `/trader-exit` | Sets the stop and the target before you enter. |
| `/trader-timemachine` | Replays 10,000 simulated sessions and every past firing of the setup. |
| `/trader-budget` | Sizes the position to your budget and your max loss per trade. |
| `/trader-risk` | Checks the order against your limits and blocks anything over them. |
| `/trader-broker` | Prepares a plain ticket you place by hand in your own broker's app. Sends nothing. |
| `/trader-alerts` | Rings when a price, your stop, your target or the opening bell is hit. |

```
scanner -> news -> entry -> exit -> timemachine -> budget -> risk -> broker ticket (you place it)
                                   alerts watches the stop, the target and flat-by
```

## Market rules built in

- NSE cash session 9:15 AM to 3:30 PM IST, Monday to Friday.
- Opening range = the 9:15, 9:20 and 9:25 five-minute bars. The first possible
  breakout bar closes at 9:35 AM. Default no new entries before 9:35 or after 3:00 PM.
- Default flat-by time 3:10 PM: brokers square off intraday (MIS) positions
  themselves around 3:15 to 3:25 PM, at a price you do not choose.
- Prices are multiples of the NSE tick, Rs 0.05.
- Orders are NSE equity, product MIS (intraday), long side only. trader-risk
  blocks delivery (CNC), carry-forward (NRML), margin, short selling and options
  unless your config allows them.
- The holiday list is the 2026 NSE calendar. For any other year every weekday
  counts as open, with a warning. Special weekend sessions (a Budget-day
  Saturday, Muhurat trading) are not in it.
- Many Indian brokers no longer offer bracket orders, so a trade is three
  orders placed by hand: the BUY, a stop-loss SELL and a target SELL. When one
  of the two SELLs fills, you cancel the other.

## Run it

Run every command from the folder that contains the skill folders; a `trader/`
folder is created there for the shared files. On Windows use `python` or `py`.

```
python trader-scanner\scan.py universe              # NSE EQ-series stocks (or: universe --source nifty500)
python trader-scanner\scan.py daily                 # after the close or before the open
python trader-scanner\scan.py orb                   # after 9:35 AM IST on a trading day
```

Then, for a stock you picked: `trader-news\news.py`, `trader-entry\entry.py`,
`trader-exit\exit.py`, `trader-timemachine\timemachine.py`,
`trader-budget\size.py`, `trader-risk\check.py`, `trader-broker\ticket.py`.
Each folder's `SKILL.md` lists its commands. To use them as Claude skills, copy
the `trader-*` folders into your skills folder.

## Limits you should know

- Yahoo's endpoints are free, unofficial and delayed; NSE data on them can lag
  or be missing. The price your broker fills at is the one that counts.
- Exchange announcements (results, board meetings, shareholding changes, bulk
  and block deals) live on the NSE and BSE announcement pages. trader-news does
  not read them: check them for any stock you trade.
- The config keys keep their old `_usd` endings (for example
  `max_loss_per_trade_usd`) so the files still fit together. In this edition
  every one of those amounts is in rupees.
- Tested offline on synthetic data only. The live Yahoo and NSE downloads have
  not been run by the author of this edition.

## Layout

```
trader-scanner/     SKILL.md, scan.py
trader-news/        SKILL.md, news.py
trader-entry/       SKILL.md, entry.py
trader-exit/        SKILL.md, exit.py
trader-timemachine/ SKILL.md, timemachine.py
trader-budget/      SKILL.md, size.py, config.example.json, targets.example.json
trader-risk/        SKILL.md, check.py
trader-broker/      SKILL.md, ticket.py
trader-alerts/      SKILL.md, alerts.py, alerts.example.json
```

MIT licensed. Adapted from github.com/Jakeschincariol/day-trader-skill.
