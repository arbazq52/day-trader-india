---
name: trader-news
description: >-
  News Monitor (India, NSE). Tracks news on every stock you watch and flags
  what moves it: Yahoo Finance headlines per ticker (SYMBOL.NS) and how far
  each stock is from the previous trading day's close. Shows only what is new
  since the last check, newest first, in IST, tags each item (earnings, board,
  holding, analyst, deal, halt, regulatory, macro...) and never repeats one.
  Exchange filings (board meetings, results, shareholding, bulk/block deals)
  are on the NSE and BSE announcement pages and are not fetched. Use when the
  user says "any news on RELIANCE", "why is this moving", "what's the news on
  my watchlist", "morning briefing", "pre-market news", "monitor the news",
  "did anything break", "check the announcements", or after /trader-scanner
  finds setups.
argument-hint: "[symbols]"
---

# trader-news

A chart can look perfect and still be about to gap on a results date, a halt
or a regulatory order. Before a setup becomes a trade, this skill reads the
Yahoo Finance headline feed for every stock on the watchlist and tells you
only what is new. It also prints how far each stock is from the previous
trading day's close, so a headline and a move sit side by side.

Tool in this folder (standard library Python, no keys):

```bash
python3 "${CLAUDE_SKILL_DIR}/news.py"                         # watchlist + plan + portfolio
python3 "${CLAUDE_SKILL_DIR}/news.py" --tickers RELIANCE TCS M&M --hours 12
python3 "${CLAUDE_SKILL_DIR}/news.py" --no-moves --json
```

Symbols are plain NSE symbols (RELIANCE, M&M, BAJAJ-AUTO); the tool adds
`.NS` for Yahoo. All times are IST (UTC+5:30), never the machine's zone.

## What it reads and writes

| file / feed | what |
| --- | --- |
| `--tickers`, else `trader/watchlist.json` | the scanner's hits (trader-scanner) |
| `trader/plan.json` | the trade you are planning (trader-exit) |
| `trader/portfolio.json` | what you hold (trader-broker records fills there) |
| Yahoo Finance headline RSS | `https://feeds.finance.yahoo.com/rss/2.0/headline?s=RELIANCE.NS&region=IN&lang=en-IN` |
| Yahoo Finance chart endpoint | the last price against the close of the previous NSE trading day (unofficial, can lag) |
| `trader/state/news.json` | what has been shown (kept 30 days) |

## Exchange filings are not fetched

Board meetings, quarterly results, shareholding pattern changes, promoter
pledges and bulk/block deals are published on the NSE and BSE announcement
pages (nseindia.com, bseindia.com). This tool does not read them. For any
stock you trade, check those pages yourself, and say so in the brief: a
headline feed can miss or lag a filing.

## The rules

- **Headlines are leads, not facts.** Before telling the user something
  happened, open the story and read it. Quote the source and link it. Never
  summarise a paywalled story you could not read: say so.
- **Say what it touches.** Every item lists the tickers it touches and its
  tags: earnings (results, quarterly results), analyst, legal, deal (order
  wins, acquisitions), capital (dividend, bonus, stock split), board (board
  meeting, record date), holding (promoter, pledge, block deal), people, risk,
  halt, regulatory (SEBI, RBI, approvals), macro (Nifty, Sensex, Budget, rate
  cut, FII/DII).
- **MOVING** marks a stock 3 % or more from the previous close
  (`--move-pct`). A move with no headline is worth saying out loud too.
- **No predictions.** Report what was published and how far the price is from
  the previous close. Never say what the stock will do next.

## Steps

1. Run the check: `python3 "${CLAUDE_SKILL_DIR}/news.py"`. Exit code 1 means
   nothing new. `--all` shows items already seen, `--json` gives everything
   machine readable, `--dry-run` leaves the state alone.
2. Read the items that matter: anything tagged earnings, board, holding,
   halt, legal, regulatory or risk, and every MOVING ticker first.
3. Write a short brief, per ticker: what happened, the source and link, the
   move, and one line on why it matters to the setup (for example "results
   season: a stock can gap at the open past any stop").
4. Tell the user to check the NSE/BSE announcements for each stock they
   plan to trade, since this tool does not fetch them.
5. If a story changes the picture, say so before `/trader-entry` and
   `/trader-exit`: a results or board meeting date inside the trade, a halt,
   a circuit limit, an offering. Never act on a headline alone.

During the session: `/loop 15m /trader-news`, or a scheduled task each
morning before the 9:15 AM IST open.

## Example (illustrative: invented numbers, not real data)

Monday, RELIANCE breaks its opening range at 10:05 AM IST. The check at
10:05 leads with "Reliance Q2 results beat estimates; board approves
dividend" (9:40 AM IST, tags: earnings, capital, board) and "SEBI order;
Nifty rate cut hopes" (8:30 AM IST, tags: regulatory, macro). The brief:
"Results are out, so the gap is already in the price; check the NSE
announcement for the exact numbers, since this tool does not read filings."
The price line reads `RELIANCE  Rs 1,300.00 +2.25% vs previous close
(13 Nov) Rs 1,271.40 at 10:05 IST`. When a ticker has no news, say so rather
than padding the brief.

## What it never does

- Never invents or embellishes a story, a quote or a number.
- Never trades on news, and never tells the user to buy or sell because of a
  headline.
- Never hammers a server: one request per feed per ticker, with a pause
  between calls.

## Safety

- Education and tooling, not investment advice, and not a SEBI-registered research or advisory service.
  This skill only reads and reports; nothing it prints is a recommendation.
- Nothing in this pack can place an order. trader-broker only prepares a ticket that the user places by
  hand in their own broker's app, after trader-risk passed that exact order today. There is no broker
  connection and no broker keys anywhere.
- Intraday equity only, long side only. No futures, options, short selling or leverage unless the config
  allows it and the user confirms.
- Brokerage, STT, exchange charges, GST and stamp duty come off every trade, and intraday equity profits
  are taxed in India as business income: tax and costs are the user's to check with a chartered
  accountant.
