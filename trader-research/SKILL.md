---
name: trader-research
description: >-
  Stock Research (India: NSE, BSE, IST, rupees). Give it ONE NSE symbol and it
  asks NSE, BSE, Yahoo Finance, Screener and Google News what they know, then
  groups it: quarterly and annual results (sales, operating profit, net profit,
  EPS, change on the year before), board meetings and record dates, corporate
  actions (dividend, bonus, split, buyback, fund-raising), orders, deals and
  partnerships, bulk and block deals, shareholding, legal and regulatory
  notices, and news, newest first with dates, sources and links. Each source
  is reported OK, PARTIAL or FAILED with the reason; nothing is invented. Use
  when the user says "research RELIANCE", "what is happening with TCS", "latest
  results", "any corporate actions", "bulk deals", "any big orders", "filings
  for INFY", "profit and loss", "quarterly results", "is a dividend coming",
  or before /trader-news and /trader-entry on a stock you do not know.
argument-hint: "SYMBOL"
---

# trader-research

The Stock Research skill answers "what is going on with this company?" for one
stock, from free public sources. It reads and summarises. It never says buy or
sell, never forecasts, and never places anything. A filing or a headline is a
lead: open the document at its link before acting on it.

All times are Indian Standard Time (IST). Money from Screener is in Rs crore
(1 crore = 10 million rupees). NSE's own results rows are in the units NSE
filed (usually Rs lakh): the line says so, check the filing.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/research.py" RELIANCE                  # everything, last 90 days
python3 "${CLAUDE_SKILL_DIR}/research.py" M&M --days 180            # longer window
python3 "${CLAUDE_SKILL_DIR}/research.py" TCS --sources screener,google
python3 "${CLAUDE_SKILL_DIR}/research.py" RELIANCE --bse-code 500325
python3 "${CLAUDE_SKILL_DIR}/research.py" INFY --json --no-write
python3 "${CLAUDE_SKILL_DIR}/research.py" INFY --show 20            # more lines per topic
```

On Windows use `python` or `py` instead of `python3`; in cmd write `"M&M"` in
quotes because `&` is special there.

Flags: `--days N` (default 90), `--sources nse,bse,yahoo,screener,google`,
`--bse-code`, `--name "Company Ltd"` (for the news search), `--show N`,
`--json`, `--no-write`, `--out-dir`, `--timeout`, `--now "2026-11-16 10:00"`
(IST), `--offline DIR` (saved files, used by the tests). Exit code 0 when at
least one source answered, 1 when none did, 2 for a bad argument.

## What it reads and writes

| file | what |
| --- | --- |
| (network) | NSE API, BSE API, Yahoo, screener.in, Google News RSS: one company, a handful of requests each |
| `trader/research_<SYMBOL>.json` | the whole report: `sources` (status per source), `market`, `financials`, `upcoming`, `items[]` (source, kind, topic, date, title, detail, url) |

Nothing else in the pack reads the file yet; it is there for the user and for
Claude to read back. `M&M` is saved as `research_M_M.json`.

## The sources

| source | gives | catch |
| --- | --- | --- |
| NSE | announcements, corporate actions, board meetings, financial results, bulk and block deals | NSE only answers something that looks like a browser with cookies. The tool opens nseindia.com first. It may still refuse (HTTP 403, or a block page): it says so |
| BSE | announcements with category and attachment links | needs BSE's numeric scrip code. Looked up by name; if the lookup is unsure it never guesses and asks for `--bse-code` (the 6 digits on the BSE quote page) |
| Yahoo | last price, 52-week range, annual and quarterly income statements, next earnings date | wants a cookie and a crumb; unofficial; delayed. Statements are often thin for Indian names |
| Screener | quarterly table, annual profit and loss, shareholding pattern | HTML scrape: a layout change or login wall makes it fail. Tries consolidated numbers, then standalone |
| Google News | headlines from news sites | headlines only, not facts; may repeat other items |

Every endpoint is unofficial and can change or block without notice. That is
why each source reports its own status: `OK`, `PARTIAL` (NSE: some of its six
endpoints answered) or `FAILED: <plain reason>`. A source with no recent
items is marked STALE with its newest date.

## Steps

1. Run `research.py SYMBOL`. If the user did not give a symbol, ask for one;
   never pick a stock for them.
2. Read the SOURCES block first and tell the user which sources answered and
   which failed. A failed source is the missing half of the picture: say so,
   do not paper over it.
3. Summarise in this order, only from what is printed:
   - **Financials**: the latest quarter against the same quarter a year ago
     (sales, operating profit, net profit, EPS) and the annual trend. Quote
     the numbers and the source; say whether Screener's basis is consolidated
     or standalone.
   - **Coming up**: board meetings, record dates, ex-dates, an earnings date
     (Yahoo's is an estimate).
   - **Corporate actions and deals**: dividend, bonus, split, buyback,
     fund-raising; orders, partnerships, acquisitions; bulk and block deals
     (who, buy or sell, how many shares, at what price).
   - **Anything legal or regulatory**, and any change of people.
4. For each important line give the date and the link. Say "the announcement
   says" for filings and "a headline says" for news.
5. If a source is blocked, show the page to open instead (see below).
6. Hand on: `/trader-news SYMBOL` for what is new since the last check,
   `/trader-entry SYMBOL` for the entry. The user decides; Claude does not.

If a source fails, the pages to open in a browser:
NSE `https://www.nseindia.com/get-quotes/equity?symbol=SYMBOL` (the Corporate
Information tab), BSE `https://www.bseindia.com/corporates/ann.html`, and
`https://www.screener.in/company/SYMBOL/consolidated/`.

## Example (illustrative: invented numbers, not real data)

```
RESEARCH: RELIANCE - Reliance Industries Ltd   as of 2026-11-14 10:00 IST   (last 90 days)

SOURCES
  nse       PARTIAL (5 of 6 NSE endpoints answered)
            - block deals: answer was not JSON: likely a block page or a changed endpoint
  bse       OK
  yahoo     OK
  screener  OK
  google    OK

FINANCIALS (screener.in, consolidated; Rs crore)
  Quarterly (latest Sep 2026)
    Sales              2,000.00  ...  2,400.00   +20.0%   (change vs 4 quarters ago)
    Net Profit           150.00  ...    180.00   +20.0%

COMING UP
  2026-11-20  Dividend - Rs 5 Per Share  (NSE)
  2026-11-28  Board meeting: Financial Results  (NSE)

DEALS, ORDERS, PARTNERSHIPS, ACQUISITIONS  [2]
  13 Nov 2026 09:15 AM IST Order win: contract awarded worth Rs 2,000 crore
                           [BSE] https://www.bseindia.com/xml-data/corpfiling/AttachLive/abc.pdf
```

Claude tells the user: "NSE answered five of six endpoints (block deals were
refused), so bulk and block deals are incomplete: check NSE's bulk-deal page.
Sales and profit are up 20 % on a year ago per Screener (consolidated). A Rs 5
dividend goes ex on 20 Nov. BSE shows an order announcement on 13 Nov: open the
attachment for the value and the counterparty."

## Rules

- Say what was checked and what was not. Quote each number with its source and date.
- A failed or empty source is "no data", never "nothing happened".
- Never invent a figure, a date or a link. Never fill a gap from memory.
- Classification (results, deal, capital...) is by keywords in the title, so
  it can be wrong: read the title and the filing.
- No price targets, no "good" or "bad" verdicts, no projections of profit or price.
- Two sources can disagree (Screener rounds; exchanges file in lakh or crore). Show both, say so.
- The tool opens public pages at a polite pace, one company at a time. Do not
  loop it over thousands of symbols.

## What it never does

It never places, sizes or checks an order, never says to buy or sell, never
logs in anywhere or reads private accounts, never calls its data real time,
and never presents a blocked or failed source as empty.

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
