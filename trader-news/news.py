#!/usr/bin/env python3
"""News monitor for trader-news, India edition (NSE, IST). Standard library only.

Watches Yahoo Finance headlines for the stocks you watch or hold and prints
only what is new since the last check, newest first, with how far each stock
is from the previous trading day's close and a flag on anything that touches
your tickers.

    python3 news.py                                  # watchlist + plan + portfolio tickers
    python3 news.py --tickers RELIANCE TCS M&M
    python3 news.py --tickers INFY --all --hours 72  # everything in the last 3 days, seen or not
    python3 news.py --no-moves                       # skip the price line per ticker

Your tickers, when --tickers is not given: every hit in trader/watchlist.json
(trader-scanner), the symbol in trader/plan.json (trader-exit) and the
positions in trader/portfolio.json. Symbols are plain NSE symbols (RELIANCE,
M&M, BAJAJ-AUTO); the tool adds .NS for Yahoo.

Sources, one request each per ticker:
  - Yahoo Finance headline RSS:
    https://feeds.finance.yahoo.com/rss/2.0/headline?s=<SYMBOL>.NS&region=IN&lang=en-IN
  - The move: Yahoo Finance's chart endpoint (unofficial, can lag), the last
    price against the close of the previous NSE trading day (the NSE holiday
    calendar decides which day that is):
    https://query2.finance.yahoo.com/v8/finance/chart/<SYMBOL>.NS?range=5d&interval=5m

NOT fetched: exchange filings. Board meetings, quarterly results, shareholding
changes and bulk/block deals are on the NSE and BSE announcement pages
(nseindia.com, bseindia.com). Check them yourself for any stock you trade.

Times print in Indian Standard Time (IST, UTC+5:30, no daylight saving; the
machine's time zone is never used). State: trader/state/news.json remembers
what you have seen (30 days), so an item shows once. Offline: --offline DIR
reads yahoo-<SYMBOL>.xml and chart-<SYMBOL>.json from DIR. The tests use it.

Headlines are leads, not facts: open the story before acting, and treat
nothing here as advice.
"""

import argparse
import datetime as _dt
import email.utils
import gzip
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

YAHOO = "https://feeds.finance.yahoo.com/rss/2.0/headline?s=%s&region=IN&lang=en-IN"
CHART = "https://%s.finance.yahoo.com/v8/finance/chart/%s?range=5d&interval=5m"
BROWSER_UA = "Mozilla/5.0 (compatible; day-trader-skill/2.0; +https://github.com/Jakeschincariol/day-trader-skill)"
KEEP_DAYS = 30
MOVE_PCT = 3.0  # a stock this far from the previous close is flagged as moving
SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9&\-]{0,19}$")

# NSE equity-segment trading holidays on weekdays, 2026 (same list as trader-scanner).
NSE_HOLIDAYS = {
    "2026-01-15": "Maharashtra Municipal Corporation Election",
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-03-26": "Shri Ram Navami",
    "2026-03-31": "Shri Mahavir Jayanti",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-28": "Bakri Id",
    "2026-06-26": "Muharram",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-10": "Diwali-Balipratipada",
    "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2026-12-25": "Christmas",
}
IST = _dt.timedelta(hours=5, minutes=30)

KEYWORDS = [
    ("earnings", r"\bearnings\b|\bresults\b|quarterly results|\bQ[1-4]\s?(?:FY)?\d{0,4}\b|\bEPS\b|\bPAT\b|\bguidance\b|\bforecast\b"),
    ("analyst", r"\bupgrade[sd]?\b|\bdowngrade[sd]?\b|price target|\boutperform\b|\bunderperform\b|\bbrokerage\b"),
    ("legal", r"\blawsuit\b|\bsued\b|\bprobe\b|\binvestigation\b|\bantitrust\b|\bjudge\b|\bcourt\b|\bNCLT\b|\bshow[- ]cause\b"),
    ("deal", r"\bacqui(?:re|res|red|sition)\b|\bmerger\b|\bbuyout\b|\btakeover\b|\bdeal\b|\border wins?\b|\bwins?\b[^.;]{0,25}\borders?\b|\border book\b|\bbags? orders?\b"),
    ("capital", r"\bdividend\b|\bbonus\b|\bbuyback\b|\brepurchase\b|\bstock split\b|\bsplit\b|\boffering\b|\bQIP\b|\brights issue\b|\bIPO\b"),
    ("board", r"\bboard meeting\b|\bboard (?:approves|to consider|meets)\b|\brecord date\b|\bAGM\b"),
    ("holding", r"\bpromoters?\b|\bpledg\w*\b|\bblock deals?\b|\bbulk deals?\b|\bstake (?:sale|buy)\b|\bshareholding\b"),
    ("people", r"\bCEO\b|\bCFO\b|\bmanaging director\b|\bresign|\bsteps down\b|\bappoint"),
    ("risk", r"\brecall\b|\bbankrupt|\bdefault\b|\bdelist|\bhack|\bbreach\b|\boutage\b|\binsolvency\b|\bfraud\b"),
    ("halt", r"\bhalt(?:s|ed)?\b|\btrading (?:pause|suspen)|\bcircuit\b|\bASM\b|\bGSM\b"),
    ("regulatory", r"\bSEBI\b|\bRBI\b|\bFDA\b|\bUSFDA\b|\bapproval\b|\bapproves\b|\bclinical\b|\bFTC\b|\bDOJ\b|\bCCI\b"),
    ("macro", r"\bFed\b|\bFOMC\b|\bCPI\b|\binflation\b|\bjobs report\b|\bpayrolls\b|\btariffs?\b|\bfutures\b|\bNifty\b|\bSensex\b|\bBudget\b|\brate (?:cut|hike)s?\b|\brepo rate\b|\bRBI policy\b|\bFII\b|\bDII\b|\bFPI\b|\bGDP\b"),
]


class NewsError(Exception):
    pass


# ---------------------------------------------------------------- time

def to_local(utc):
    """Aware or naive UTC -> naive IST wall-clock time. Never uses the machine's zone."""
    if utc.tzinfo is not None:
        utc = utc.astimezone(_dt.timezone.utc)
    return utc.replace(tzinfo=None) + IST


def local_to_utc(local):
    """Naive IST -> aware UTC."""
    return (local - IST).replace(tzinfo=_dt.timezone.utc)


def ts_to_local(ts):
    """Unix seconds -> naive IST."""
    return _dt.datetime(1970, 1, 1) + _dt.timedelta(seconds=int(ts)) + IST


def is_trading_day(d):
    """Weekdays that are not on the 2026 NSE holiday list. Other years: any weekday."""
    return d.weekday() < 5 and d.isoformat() not in NSE_HOLIDAYS


def previous_trading_day(d):
    """The NSE trading day before date d."""
    d = d - _dt.timedelta(days=1)
    while not is_trading_day(d):
        d -= _dt.timedelta(days=1)
    return d


def date_label(d):
    return "%d %s" % (d.day, d.strftime("%b"))


# ---------------------------------------------------------------- inputs

def load_json(path):
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    return None


def normalize(sym):
    """Plain NSE symbol: upper case, any .NS / .BO stripped. None if it is not a valid symbol."""
    s = str(sym or "").upper().strip()
    if s.endswith((".NS", ".BO")):
        s = s[:-3]
    return s if SYMBOL_RE.match(s) else None


def watch_from_files(portfolio="trader/portfolio.json", watchlist="trader/watchlist.json",
                     plan="trader/plan.json"):
    """{symbol: name or None}: the scanner's hits, the planned trade and your holdings."""
    out = {}

    def add(sym, name, override=False):
        s = normalize(sym)
        if not s:
            return
        if override:
            out[s] = name or out.get(s)
        else:
            out.setdefault(s, name)

    wl = load_json(watchlist) or {}
    for h in wl.get("hits", []):
        add(h.get("symbol") or h.get("ticker"), h.get("name"), True)
    pl = load_json(plan) or {}
    add(pl.get("symbol"), pl.get("name"))
    pf = load_json(portfolio) or {}
    for p in pf.get("positions", []):
        add(p.get("ticker") or p.get("symbol"), p.get("name"), True)
    return out


# ---------------------------------------------------------------- fetching

class Fetcher(object):
    def __init__(self, offline=None, pause=0.15):
        self.offline = offline
        self.pause = pause
        self._last = 0.0

    def get(self, url, name):
        if self.offline:
            path = os.path.join(self.offline, name)
            if not os.path.isfile(path):
                raise NewsError("offline: no file %s" % path)
            with open(path, "rb") as fh:
                return fh.read()
        gap = time.time() - self._last
        if gap < self.pause:
            time.sleep(self.pause - gap)
        self._last = time.time()
        headers = {"User-Agent": BROWSER_UA, "Accept-Encoding": "gzip"}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as exc:
            raise NewsError("HTTP %s for %s" % (exc.code, url))
        except urllib.error.URLError as exc:
            raise NewsError("could not reach %s: %s" % (url, exc.reason))


def to_yahoo(sym):
    """NSE symbol -> Yahoo symbol (RELIANCE -> RELIANCE.NS)."""
    s = sym.upper().strip()
    return s if s.endswith((".NS", ".BO")) else s + ".NS"


def from_yahoo(ysym):
    """Yahoo symbol -> NSE symbol (RELIANCE.NS -> RELIANCE)."""
    s = ysym.upper().strip()
    return s[:-3] if s.endswith((".NS", ".BO")) else s


def yahoo_q(sym):
    """URL-quoted Yahoo symbol: M&M -> M%26M.NS."""
    return urllib.parse.quote(to_yahoo(sym), safe="")


# ---------------------------------------------------------------- parsing

def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _text(el, name):
    for c in el.iter():
        if _local(c.tag) == name:
            return (c.text or "").strip()
    return ""


def parse_time(value):
    """RFC 822 (RSS) or ISO 8601 (Atom) -> aware UTC datetime, or None."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        d = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        d = None
    if d is None:
        try:
            d = _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d.astimezone(_dt.timezone.utc)


def parse_now(text):
    """--now: ISO time -> aware UTC. A time without an offset is taken as IST."""
    t = (text or "").strip().replace("Z", "+00:00")
    try:
        d = _dt.datetime.fromisoformat(t)
    except ValueError:
        raise NewsError('--now wants a time like "2026-11-16 10:00" (IST) or ...Z (UTC)')
    if d.tzinfo is None:
        return local_to_utc(d)
    return d.astimezone(_dt.timezone.utc)


def parse_rss(data, ticker):
    """Yahoo headline RSS -> items."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise NewsError("RSS for %s is not valid XML: %s" % (ticker, exc))
    out = []
    for it in root.iter("item"):
        title = _text(it, "title")
        link = _text(it, "link")
        guid = _text(it, "guid") or link
        out.append({"id": "rss:" + guid, "source": "Yahoo Finance", "kind": "headline",
                    "ticker": ticker, "title": title, "summary": _text(it, "description"),
                    "link": link, "time": parse_time(_text(it, "pubDate"))})
    return out


def parse_chart(data, ticker):
    """Yahoo chart JSON (5 days of 5-minute bars) ->
    {"ticker", "price", "prev_close", "prev_date", "pct", "time"} or raise.

    The previous close is the last bar of the previous NSE trading day (calendar
    above). If the bars do not reach back that far, Yahoo's previousClose is used
    only when the data is a one-day range; chartPreviousClose of a longer range is
    the close before the range starts and is never used."""
    try:
        doc = json.loads(data.decode("utf-8") if isinstance(data, bytes) else data)
        res = doc["chart"]["result"][0]
        meta = res["meta"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise NewsError("chart for %s is not usable" % ticker)
    stamps = res.get("timestamp") or []
    closes = (((res.get("indicators") or {}).get("quote") or [{}])[0] or {}).get("close") or []
    bars = [(ts_to_local(t), float(c)) for t, c in zip(stamps, closes) if t is not None and c is not None]
    price = meta.get("regularMarketPrice")
    when = meta.get("regularMarketTime")
    if not price and bars:
        price = bars[-1][1]
    if not when and bars:
        when = stamps[len(bars) - 1]
    if not price:
        raise NewsError("chart for %s has no price" % ticker)
    last_local = ts_to_local(when) if when else (bars[-1][0] if bars else None)
    prev = prev_date = None
    if last_local is not None:
        want = previous_trading_day(last_local.date()) if is_trading_day(last_local.date()) \
            else None
        if want is None:  # last price is from a non-trading day: use the latest earlier session
            want = last_local.date()
            while not is_trading_day(want):
                want -= _dt.timedelta(days=1)
            if not any(b[0].date() == want for b in bars):
                want = previous_trading_day(want + _dt.timedelta(days=1))
        day_bars = [b for b in bars if b[0].date() == want]
        if day_bars:
            prev, prev_date = day_bars[-1][1], want
    if prev is None:
        rng = meta.get("range") or ""
        if rng in ("", "1d"):
            prev = meta.get("previousClose") or meta.get("chartPreviousClose")
        else:
            prev = meta.get("previousClose")
    if not prev:
        raise NewsError("chart for %s has no previous close" % ticker)
    return {"ticker": ticker, "price": round(float(price), 2), "prev_close": round(float(prev), 2),
            "prev_date": prev_date.isoformat() if prev_date else None,
            "pct": round((float(price) / float(prev) - 1) * 100, 2),
            "time": _dt.datetime.fromtimestamp(when, _dt.timezone.utc) if when else None}


def collect_moves(fetcher, watch, errors=None):
    errors = [] if errors is None else errors
    out = []
    for t in sorted(watch):
        name = "chart-%s.json" % t
        try:
            try:
                data = fetcher.get(CHART % ("query2", yahoo_q(t)), name)
            except NewsError as exc:
                if fetcher.offline or not re.search(r"HTTP (429|5\d\d)", str(exc)):
                    raise
                data = fetcher.get(CHART % ("query1", yahoo_q(t)), name)
            out.append(parse_chart(data, t))
        except NewsError as exc:
            if not (fetcher.offline and "no file" in str(exc)):
                errors.append("price for %s: %s" % (t, exc))
    return out


def mention_patterns(watch):
    pats = {}
    for t, name in watch.items():
        e = re.escape(t)
        alts = [r"\(%s\)" % e,
                r"\b(?:NSE|BSE|NSEI)\s*:\s*%s(?![A-Za-z0-9&\-])" % e]
        if name and len(name) >= 4:
            alts.append(r"\b%s\b" % re.escape(name).replace(r"\ ", r"[\s-]"))
        pats[t] = re.compile("|".join(alts))
    return pats


def tag(items, watch):
    """Which of your tickers each item touches, and why it matters."""
    pats = mention_patterns(watch)
    for it in items:
        hay = "%s %s" % (it["title"], it.get("summary") or "")
        touches = {it["ticker"]} if it["ticker"] in watch else set()
        for t, rx in pats.items():
            if rx.search(hay):
                touches.add(t)
        it["touches"] = sorted(touches)
        it["tags"] = [label for label, rx in KEYWORDS if re.search(rx, hay, re.I)]
    return items


def dedupe(items):
    """One item per story: same id, or same link, or same title the same day."""
    seen, out = {}, []
    for it in items:
        keys = [it["id"], it["link"],
                "%s|%s" % (re.sub(r"\W+", " ", it["title"].lower()).strip(),
                           to_local(it["time"]).date() if it["time"] else "")]
        hit = next((seen[k] for k in keys if k and k in seen), None)
        if hit is not None:
            for t in it.get("touches", []):
                if t not in hit["touches"]:
                    hit["touches"].append(t)
            hit["touches"].sort()
            continue
        for k in keys:
            if k:
                seen[k] = it
        out.append(it)
    return out


def fingerprint(it):
    return hashlib.sha1(it["id"].encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- the check

def collect(fetcher, watch, errors=None):
    errors = [] if errors is None else errors
    items = []
    for t in sorted(watch):
        try:
            items += parse_rss(fetcher.get(YAHOO % yahoo_q(t), "yahoo-%s.xml" % t), t)
        except NewsError as exc:
            errors.append("headlines for %s: %s" % (t, exc))
    return items


def select(items, state, now, hours=48, show_all=False):
    """Items within the window; only unseen ones unless show_all."""
    seen = state.setdefault("seen", {})
    cutoff = now - _dt.timedelta(hours=hours)
    ahead = now + _dt.timedelta(minutes=10)  # a pinned --now: nothing from after it
    out = []
    for it in items:
        if it["time"] is not None and (it["time"] < cutoff or it["time"] > ahead):
            continue
        fp = fingerprint(it)
        it["new"] = fp not in seen
        if it["new"] or show_all:
            out.append(it)
    out.sort(key=lambda i: (i["time"] or now), reverse=True)
    return out


def remember(items, state, now):
    seen = state.setdefault("seen", {})
    stamp = now.isoformat()
    for it in items:
        seen.setdefault(fingerprint(it), stamp)
    cutoff = (now - _dt.timedelta(days=KEEP_DAYS)).isoformat()
    state["seen"] = {k: v for k, v in seen.items() if v >= cutoff}
    state["last_check"] = stamp


def render_moves(moves, move_pct=MOVE_PCT):
    out = []
    for m in moves:
        flag = "MOVING" if abs(m["pct"]) >= move_pct else ""
        when = (" at %s IST" % to_local(m["time"]).strftime("%H:%M")) if m.get("time") else ""
        pd = _dt.date.fromisoformat(m["prev_date"]) if m.get("prev_date") else None
        prev = "previous close%s Rs %s" % ((" (%s)" % date_label(pd)) if pd else "",
                                           "{:,.2f}".format(m["prev_close"]))
        out.append("%-11s Rs %s %+.2f%% vs %s%s  %s" % (
            m["ticker"], "{:,.2f}".format(m["price"]), m["pct"], prev, when, flag))
    return out


def render(items, errors, now, moves=None, move_pct=MOVE_PCT):
    out = render_moves(moves or [], move_pct)
    if out:
        out.append("")
    if not items:
        out.append("Nothing new.")
    for it in items:
        when = to_local(it["time"]).strftime("%Y-%m-%d %H:%M IST") if it["time"] else "time unknown"
        who = ",".join(it["touches"]) or it["ticker"]
        out.append("  %s  %-11s %-13s %s" % (when, who, it["source"], it["title"]))
        extra = []
        if it["tags"]:
            extra.append("tags: " + ", ".join(it["tags"]))
        extra.append(it["link"])
        out.append("      " + "  ".join(extra))
    for e in errors:
        out.append("note: %s" % e)
    out.append("Exchange filings (board meetings, results, shareholding, bulk/block deals) are not "
               "fetched: check NSE/BSE announcements.")
    out.append("Checked %s. Headlines are leads, not facts; open the story before acting. "
               "Not investment advice." % to_local(now).strftime("%Y-%m-%d %H:%M IST"))
    return "\n".join(out) + "\n"


def _json_ready(items):
    out = []
    for it in items:
        d = dict(it)
        d["time"] = it["time"].isoformat() if it["time"] else None
        out.append(d)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tickers", nargs="*", help="default: watchlist + plan + portfolio")
    ap.add_argument("--portfolio", default="trader/portfolio.json")
    ap.add_argument("--watchlist", default="trader/watchlist.json")
    ap.add_argument("--plan", default="trader/plan.json")
    ap.add_argument("--state", default="trader/state/news.json")
    ap.add_argument("--hours", type=float, default=48, help="ignore items older than this")
    ap.add_argument("--all", action="store_true", help="show seen items too")
    ap.add_argument("--no-moves", action="store_true", help="skip the price line per ticker")
    ap.add_argument("--move-pct", type=float, default=MOVE_PCT, help="flag a move this big (percent)")
    ap.add_argument("--offline", metavar="DIR")
    ap.add_argument("--now", help='ISO time, for reproducible runs; no offset means IST, 2026-11-16T10:00:00Z is UTC')
    ap.add_argument("--dry-run", action="store_true", help="do not update the state file")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if args.tickers:
        bad = [t for t in args.tickers if not normalize(t)]
        if bad:
            print("news: not an NSE symbol: %s (use plain symbols like RELIANCE, M&M, BAJAJ-AUTO)"
                  % ", ".join(bad), file=sys.stderr)
            return 2
        watch = {normalize(t): None for t in args.tickers}
        known = watch_from_files(args.portfolio, args.watchlist, args.plan)
        watch.update({t: known[t] for t in watch if known.get(t)})
    else:
        watch = watch_from_files(args.portfolio, args.watchlist, args.plan)
    if not watch:
        print("news: no tickers. Pass --tickers, or run /trader-scanner first (it writes "
              "trader/watchlist.json).", file=sys.stderr)
        return 2
    now = parse_now(args.now) if args.now else _dt.datetime.now(_dt.timezone.utc)
    state = load_json(args.state) or {}
    errors = []
    fetcher = Fetcher(offline=args.offline)
    items = collect(fetcher, watch, errors=errors)
    items = dedupe(tag(items, watch))
    shown = select(items, state, now, hours=args.hours, show_all=args.all)
    moves = [] if args.no_moves else collect_moves(fetcher, watch, errors)
    if args.json:
        mv = [dict(m, time=m["time"].isoformat() if m.get("time") else None,
                   moving=abs(m["pct"]) >= args.move_pct) for m in moves]
        print(json.dumps({"checked": now.isoformat(), "moves": mv, "items": _json_ready(shown),
                          "notes": errors}, indent=2))
    else:
        sys.stdout.write(render(shown, errors, now, moves, args.move_pct))
    if not args.dry_run:
        remember(items, state, now)
        folder = os.path.dirname(args.state)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(args.state, "w", encoding="utf-8") as fh:
            json.dump(state, fh, indent=2)
            fh.write("\n")
    return 0 if any(i["new"] for i in shown) else 1


if __name__ == "__main__":
    sys.exit(main())
