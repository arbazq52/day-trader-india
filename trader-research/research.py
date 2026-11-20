#!/usr/bin/env python3
"""Stock research for trader-research, India edition (NSE, BSE, IST). Standard library only.

Give it ONE NSE symbol. It asks several free public sources what they know
about that company and prints what it found, grouped, newest first, each line
with its date, its source and a link when there is one.

    python3 research.py RELIANCE
    python3 research.py M&M --days 180
    python3 research.py TCS --json --no-write
    python3 research.py INFY --sources google,yahoo,screener
    python3 research.py RELIANCE --bse-code 500325
    python3 research.py RELIANCE --offline saved_files/

Sources (each is tried alone; one failing never stops the others):
  nse       NSE's website API: announcements, corporate actions, board meetings,
            financial results, bulk and block deals. NSE only answers a browser
            that holds its cookies, so this tool first opens nseindia.com like a
            browser would. NSE may still refuse: that is reported, not hidden.
  bse       BSE's announcements API (api.bseindia.com). Needs BSE's numeric
            scrip code: found by a lookup, or give --bse-code.
  yahoo     Yahoo Finance: price, 52-week range and income statements
            (quarterly and annual). Yahoo wants a cookie and crumb first.
  screener  screener.in company page: the quarterly and the profit-and-loss tables.
  google    Google News RSS for the company name or symbol.

All of these are free, unofficial and can change or block without warning.
Nothing here is real time. Every item shows its own date, and a source whose
newest item is old says so. Nothing is invented: a source that gave nothing
prints "no data" with the reason.

Times are Indian Standard Time (IST, UTC+5:30; the machine's zone is never used).
Money from Screener is in Rs crore (Rs Cr; 1 crore = 10 million rupees).

Offline: --offline DIR reads saved files instead of the network:
  nse-announcements.json nse-actions.json nse-board.json nse-results.json
  nse-bulk.json nse-block.json bse-announcements.json bse-lookup.json
  yahoo-summary.json yahoo-chart.json screener.html google-news.xml
The tests use it.

Output file: trader/research_<SYMBOL>.json (skip with --no-write).
Headlines and filings are leads, not advice: open the document before acting.
"""

import argparse
import datetime as _dt
import email.utils
import gzip
import html
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

IST = _dt.timedelta(hours=5, minutes=30)
SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9&\-]{0,19}$")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 20
STALE_DAYS = 45          # a source whose newest item is older than this is flagged
ALL_SOURCES = ("nse", "bse", "yahoo", "screener", "google")

NSE_HOME = "https://www.nseindia.com/"
NSE_API = "https://www.nseindia.com/api/"
BSE_API = "https://api.bseindia.com/BseIndiaAPI/api/"
BSE_FILES = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
NSE_FILES = "https://nsearchives.nseindia.com/"

# Topic rules: first match wins, so the specific ones come first.
TOPICS = [
    ("results", r"financial results?|quarterly results?|\bresults?\b|\bQ[1-4]\s?(?:FY)?\s?\d{0,4}\b|\bPAT\b|"
                r"\bEPS\b|earnings|unaudited|audited|profit after tax|net profit"),
    ("deal", r"\bacqui(?:re|res|red|sition)\b|\bmerger\b|\bamalgamation\b|\bdemerger\b|\bjoint venture\b|\bJV\b|"
             r"\bpartnership\b|\bpartners?\b|\bMoU\b|memorandum of understanding|\bcollaborat\w*|\btie[- ]?up\b|"
             r"\bstrategic alliance\b|\border[s]?\b|\bcontract\b|\bbags?\b|\bawarded\b|\bletter of (?:award|intent)\b|"
             r"\bLoA\b|\bLoI\b|\bagreement\b|\bslump sale\b|\bstake (?:sale|buy|acquisition)\b"),
    ("capital", r"\bdividend\b|\bbonus\b|\bbuy-?back\b|\bsplit\b|sub-?division\b|\brights?\b|\bQIP\b|\bpreferential\b|"
                r"\bwarrants?\b|\bNCD\b|\bdebentures?\b|\bfund ?rais\w*|\bFPO\b|\bIPO\b|\bOFS\b|\bESOP\b|"
                r"\bcapital reduction\b|\bdemerger\b|\bscheme of arrangement\b"),
    ("board", r"board meeting|\bAGM\b|\bEGM\b|annual general meeting|extra-?ordinary general|record date|"
              r"book closure|intimation of"),
    ("holding", r"\bshareholding pattern\b|\bpromoters?\b|\bpledg\w*|\binvocation\b|\bencumbrance\b|"
                r"\bSAST\b|\binsider\b|\bPIT\b|\btrading window\b|\bbulk deal\b|\bblock deal\b"),
    ("people", r"\bCEO\b|\bCFO\b|\bCOO\b|managing director|\bchairman\b|\bresign\w*|\bappoint\w*|\bdirector\b|"
               r"company secretary|key managerial|\bauditor\b|senior management"),
    ("legal", r"\bcourt\b|\bNCLT\b|\bNCLAT\b|\btribunal\b|\bSEBI\b|\bshow[- ]cause\b|\bpenalt\w*|\bfine\b|"
              r"\binvestigation\b|\braid\b|\bnotice\b|\bprobe\b|\bED\b|\bCBI\b|\bGST (?:demand|order)\b|"
              r"\bincome tax\b|\bdefault\b|\binsolvency\b|\bfraud\b|\bdisclosure under regulation 30\b"),
    ("rating", r"\bcredit rating\b|\bCRISIL\b|\bICRA\b|\bCARE\b|\bIndia Ratings\b|\bupgrade[sd]?\b|\bdowngrade[sd]?\b|"
               r"price target|\bbrokerage\b|\boutperform\b|\bunderperform\b|\bbuy rating\b|\bsell rating\b"),
]
TOPIC_ORDER = ["results", "deal", "capital", "board", "holding", "people", "legal", "rating", "other"]
TOPIC_TITLES = {
    "results": "Results and earnings", "deal": "Deals, orders, partnerships, acquisitions",
    "capital": "Corporate actions and capital (dividend, split, bonus, buyback, fund-raising)",
    "board": "Board meetings, AGM and record dates", "holding": "Shareholding, promoters, insider and bulk deals",
    "people": "People and governance", "legal": "Legal, regulatory and compliance",
    "rating": "Ratings and brokerages", "other": "Other announcements and news",
}
_TOPIC_RE = [(name, re.compile(rx, re.I)) for name, rx in TOPICS]


class ResearchError(Exception):
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


def now_ist():
    return to_local(_dt.datetime.now(_dt.timezone.utc))


def parse_now(text):
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(text.strip(), fmt)
        except ValueError:
            pass
    raise ResearchError('--now needs "YYYY-MM-DD HH:MM" in IST, for example "2026-11-16 10:00"')


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def parse_date(value):
    """Many shapes of an exchange date -> naive IST datetime (assumed already IST), or None.

    NSE: 12-Nov-2026 16:30:00 / 12-Nov-2026 / 2026-11-12 16:30:00 / 20261112
    BSE: 2026-11-12T16:30:00 / 12 Nov 2026 / /Date(1700000000000)/
    """
    if value in (None, "", "-"):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        return ts_to_local(v / 1000 if v > 1e11 else v)
    s = str(value).strip()
    m = re.match(r"^/Date\((\d+)", s)
    if m:
        return ts_to_local(int(m.group(1)) / 1000)
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?", s)
    if m:
        return _mk(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6))
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    if m:
        return _mk(m.group(1), m.group(2), m.group(3))
    m = re.match(r"^(\d{1,2})[-\s/]([A-Za-z]{3})[A-Za-z]*[-\s/,]*(\d{4})(?:[ T,]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", s)
    if m and m.group(2).lower() in _MONTHS:
        return _mk(m.group(3), _MONTHS[m.group(2).lower()], m.group(1), m.group(4), m.group(5), m.group(6))
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})", s)
    if m:
        return _mk(m.group(3), m.group(2), m.group(1))
    try:  # RFC 822, Google News and Yahoo RSS: carries its own zone
        d = email.utils.parsedate_to_datetime(s)
        return to_local(d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc))
    except (TypeError, ValueError, IndexError):
        return None


def _mk(y, mo, d, h=None, mi=None, s=None):
    try:
        return _dt.datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0))
    except ValueError:
        return None


def fmt_dt(d):
    if d is None:
        return "no date"
    if d.hour == 0 and d.minute == 0 and d.second == 0:
        return d.strftime("%d %b %Y")
    return d.strftime("%d %b %Y %I:%M %p IST")


# ---------------------------------------------------------------- symbols

def normalize(sym):
    s = (sym or "").strip().upper()
    if s.endswith((".NS", ".BO")):
        s = s[:-3]
    if not SYMBOL_RE.match(s):
        raise ResearchError("%r is not a plain NSE symbol (letters, digits, & and -)" % sym)
    return s


def to_yahoo(sym):
    return normalize(sym) + ".NS"


def yahoo_q(sym):
    return urllib.parse.quote(to_yahoo(sym), safe="")


def file_safe(sym):
    return re.sub(r"[^A-Z0-9\-]", "_", sym)


# ---------------------------------------------------------------- fetching

class Fetcher:
    """Network (with cookies, browser headers, one retry) or a folder of saved files."""

    def __init__(self, offline=None, timeout=TIMEOUT, pause=0.4):
        self.offline = offline
        self.timeout = timeout
        self.pause = pause
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self._warmed = set()
        self._last = 0.0

    def saved(self, name):
        path = os.path.join(self.offline, name)
        if not os.path.exists(path):
            raise ResearchError("no saved file %s" % name)
        with open(path, "rb") as f:
            return f.read()

    def get(self, url, headers=None, saved=None):
        """Return the body as bytes. Raises ResearchError with a plain reason."""
        if self.offline is not None:
            return self.saved(saved)
        wait = self.pause - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-IN,en;q=0.9",
             "Accept-Encoding": "gzip"}
        h.update(headers or {})
        last = None
        for attempt in (1, 2):
            try:
                req = urllib.request.Request(url, headers=h)
                with self.opener.open(req, timeout=self.timeout) as r:
                    data = r.read()
                    if r.headers.get("Content-Encoding") == "gzip" or data[:2] == b"\x1f\x8b":
                        data = gzip.decompress(data)
                self._last = time.time()
                return data
            except urllib.error.HTTPError as e:
                last = "HTTP %s from %s" % (e.code, urllib.parse.urlsplit(url).netloc)
                if e.code in (401, 403):
                    last += " (the site refused a script; open it in a browser instead)"
                if e.code == 429 or e.code >= 500:
                    time.sleep(3)
                    continue
                break
            except (urllib.error.URLError, OSError, ValueError) as e:
                last = "could not reach %s: %s" % (urllib.parse.urlsplit(url).netloc, getattr(e, "reason", e))
                time.sleep(1)
        self._last = time.time()
        raise ResearchError(last)

    def json(self, url, headers=None, saved=None):
        data = self.get(url, headers, saved)
        try:
            return json.loads(data.decode("utf-8-sig", "replace"))
        except ValueError:
            head = data[:60].decode("utf-8", "replace").strip().replace("\n", " ")
            raise ResearchError("answer was not JSON (%s...): likely a block page or a changed endpoint" % head)

    def warm(self, key, url, headers=None):
        """Open a home page once so the site hands out its cookies."""
        if self.offline is not None or key in self._warmed:
            return
        self._warmed.add(key)
        try:
            self.get(url, headers)
        except ResearchError:
            pass  # the real request will report the failure


# ---------------------------------------------------------------- item helpers

def pick(d, *keys, default=None):
    """First non-empty value among keys (case-insensitive) in dict d."""
    if not isinstance(d, dict):
        return default
    low = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        v = low.get(k.lower())
        if v not in (None, "", "-"):
            return v
    return default


def clean(text):
    if text is None:
        return ""
    t = html.unescape(str(text))
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def topic_of(text):
    for name, rx in _TOPIC_RE:
        if rx.search(text or ""):
            return name
    return "other"


def make_item(source, kind, when, title, detail="", url="", extra=None):
    title = clean(title)
    detail = clean(detail)
    topic = topic_of(title + " " + detail) if kind in ("announcement", "news") else {
        "result": "results", "action": "capital", "board": "board", "deal": "holding"}.get(kind, "other")
    if kind == "announcement" and topic == "other" and re.search(r"\border|contract|award", title, re.I):
        topic = "deal"
    it = {"source": source, "kind": kind, "topic": topic, "when": when.isoformat() if when else None,
          "title": title, "detail": detail if detail != title else "", "url": url}
    if extra:
        it["data"] = extra
    return it


# ---------------------------------------------------------------- NSE

def nse_headers(symbol):
    return {"Accept": "application/json, text/plain, */*", "Referer": NSE_HOME + "get-quotes/equity?symbol=" +
            urllib.parse.quote(symbol, safe=""), "X-Requested-With": "XMLHttpRequest"}


def rows_of(data):
    """NSE sometimes wraps rows as {"data": [...]}; sometimes a bare list."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("data", "Table", "rows", "result"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


def nse_file_url(name):
    name = (name or "").strip()
    if not name or name == "-":
        return ""
    return name if name.startswith("http") else NSE_FILES + name.lstrip("/")


def parse_nse_announcements(data):
    out = []
    for r in rows_of(data):
        when = parse_date(pick(r, "an_dt", "sort_date", "dt", "date"))
        title = pick(r, "desc", "subject", "sm_name", default="")
        detail = pick(r, "attchmntText", "attchmnttext", "body", default="")
        out.append(make_item("NSE", "announcement", when, title, detail,
                             nse_file_url(pick(r, "attchmntFile", "attchmntfile", "file", default=""))))
    return out


def parse_nse_actions(data):
    out = []
    for r in rows_of(data):
        subject = pick(r, "subject", "purpose", default="")
        ex = parse_date(pick(r, "exDate", "ex_date"))
        rec = parse_date(pick(r, "recDate", "rec_date"))
        bc = parse_date(pick(r, "bcStartDate"))
        bits = []
        if ex:
            bits.append("ex-date " + fmt_dt(ex))
        if rec:
            bits.append("record date " + fmt_dt(rec))
        if bc and not rec:
            bits.append("book closure from " + fmt_dt(bc))
        out.append(make_item("NSE", "action", ex or rec or bc, subject, "; ".join(bits),
                             extra={"ex_date": ex.date().isoformat() if ex else None,
                                    "record_date": rec.date().isoformat() if rec else None}))
    return out


def parse_nse_board(data):
    out = []
    for r in rows_of(data):
        when = parse_date(pick(r, "bm_date", "date", "meetingDate"))
        purpose = pick(r, "bm_purpose", "purpose", default="Board meeting")
        desc = pick(r, "bm_desc", "bm_description", "description", default="")
        out.append(make_item("NSE", "board", when, "Board meeting: " + clean(purpose), desc,
                             nse_file_url(pick(r, "attachment", "attchmntFile", default=""))))
    return out


def num(v):
    """'1,234.5', '(12.0)', '-', None -> float or None."""
    if v in (None, "", "-"):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace("%", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        x = float(s)
    except ValueError:
        return None
    return -x if neg else x


def parse_nse_results(data):
    """NSE's financial-results list: one row per filing. Amounts here are Rs lakh as filed."""
    out = []
    for r in rows_of(data):
        period_end = parse_date(pick(r, "toDate", "to_date", "qe_Date", "period_end"))
        filed = parse_date(pick(r, "broadCastDate", "filingDate", "creation_Date", "bm_date"))
        income = num(pick(r, "income", "totalIncome", "re_net_sale"))
        pat = num(pick(r, "proLossAftTax", "reProLossAftTax", "re_con_pro_loss", "netProfit"))
        eps = num(pick(r, "reDilEPS", "re_desc_eps", "eps", "re_bas_eps"))
        rel = pick(r, "relatingTo", "period", default="")
        aud = pick(r, "audited", default="")
        unit = "the units NSE filed in (usually Rs lakh): check the filing"
        bits = []
        if income is not None:
            bits.append("income %s" % money(income))
        if pat is not None:
            bits.append("profit after tax %s" % money(pat))
        if eps is not None:
            bits.append("EPS Rs %s" % ("%.2f" % eps))
        title = "Results for period ended %s%s" % (fmt_dt(period_end) if period_end else "unknown date",
                                                   " (%s)" % clean(rel) if rel else "")
        if aud:
            title += ", " + clean(aud)
        out.append(make_item("NSE", "result", filed or period_end, title,
                             "; ".join(bits) + ("; amounts in " + unit if bits else ""),
                             nse_file_url(pick(r, "xbrl", "attachment", default="")),
                             extra={"period_end": period_end.date().isoformat() if period_end else None,
                                    "income": income, "profit_after_tax": pat, "eps": eps}))
    return out


def parse_nse_deals(data, kind_label):
    out = []
    for r in rows_of(data):
        when = parse_date(pick(r, "BD_DT_DATE", "date", "mTIMESTAMP", "TIMESTAMP"))
        client = pick(r, "BD_CLIENT_NAME", "clientName", "client", default="(client not shown)")
        side = str(pick(r, "BD_BUY_SELL", "buySell", "buy_sell", default="")).upper()
        side = {"B": "BUY", "S": "SELL"}.get(side, side)
        qty = num(pick(r, "BD_QTY_TRD", "quantity", "qty"))
        px = num(pick(r, "BD_TP_WATP", "tradePrice", "price", "watp"))
        remarks = clean(pick(r, "BD_REMARKS", "remarks", default=""))
        title = "%s: %s %s %s shares%s" % (kind_label, clean(client), side or "?",
                                           "{:,.0f}".format(qty) if qty is not None else "?",
                                           " at Rs %.2f" % px if px is not None else "")
        out.append(make_item("NSE", "deal", when, title, remarks,
                             extra={"client": clean(client), "side": side, "qty": qty, "price": px,
                                    "value_rs": round(qty * px, 2) if qty is not None and px is not None else None}))
    return out


def money(v):
    return "{:,.2f}".format(v)


def collect_nse(f, symbol, since, until):
    """Returns (items, notes, ok_count, try_count). Each NSE endpoint is tried separately."""
    q = urllib.parse.quote(symbol, safe="")
    d_from, d_to = since.strftime("%d-%m-%Y"), until.strftime("%d-%m-%Y")
    f.warm("nse", NSE_HOME)
    f.warm("nse-q", NSE_HOME + "get-quotes/equity?symbol=" + q)
    h = nse_headers(symbol)
    jobs = [
        ("announcements", "corporate-announcements?index=equities&symbol=%s" % q,
         "nse-announcements.json", parse_nse_announcements),
        ("corporate actions", "corporates-corporateActions?index=equities&symbol=%s" % q,
         "nse-actions.json", parse_nse_actions),
        ("board meetings", "corporate-board-meetings?index=equities&symbol=%s" % q,
         "nse-board.json", parse_nse_board),
        ("financial results", "corporates-financial-results?index=equities&symbol=%s&period=Quarterly" % q,
         "nse-results.json", parse_nse_results),
        ("bulk deals", "historical/bulk-deals?symbol=%s&from=%s&to=%s" % (q, d_from, d_to),
         "nse-bulk.json", lambda d: parse_nse_deals(d, "Bulk deal")),
        ("block deals", "historical/block-deals?symbol=%s&from=%s&to=%s" % (q, d_from, d_to),
         "nse-block.json", lambda d: parse_nse_deals(d, "Block deal")),
    ]
    items, notes, ok = [], [], 0
    for label, path, saved, parser in jobs:
        try:
            data = f.json(NSE_API + path, h, saved)
            got = parser(data)
            items.extend(got)
            ok += 1
            if not got:
                notes.append("%s: none listed" % label)
        except ResearchError as e:
            notes.append("%s: %s" % (label, e))
    return items, notes, ok, len(jobs)


# ---------------------------------------------------------------- BSE

def bse_headers():
    return {"Accept": "application/json, text/plain, */*", "Origin": "https://www.bseindia.com",
            "Referer": "https://www.bseindia.com/"}


def find_bse_code(f, symbol, name_hint=None):
    """Look the scrip code up. Returns (code, note). Never guesses between several matches."""
    try:
        data = f.json(BSE_API + "fetchComp/w?size=10&text=" + urllib.parse.quote(symbol, safe=""),
                      bse_headers(), "bse-lookup.json")
    except ResearchError as e:
        return None, "code lookup failed (%s); pass --bse-code" % e
    rows = rows_of(data) or (data if isinstance(data, list) else [])
    cands = []
    for r in rows:
        code = str(pick(r, "scrip_cd", "SCRIP_CD", "scripcode", "SecurityCode", default="")).strip()
        sid = str(pick(r, "scrip_id", "SCRIP_ID", "SecurityId", "symbol", default="")).strip().upper()
        nm = clean(pick(r, "scrip_name", "Scrip_Name", "SCRIP_NAME", "LONG_NAME", "name", default=""))
        if re.fullmatch(r"\d{5,6}", code):
            cands.append((code, sid, nm))
    exact = [c for c in cands if c[1] == symbol]
    if len(exact) == 1:
        return exact[0][0], "BSE code %s (%s)" % (exact[0][0], exact[0][2] or exact[0][1])
    if len(cands) == 1 and not exact:
        c = cands[0]
        return None, "one BSE match, %s (%s), but its id is not %s: check it and pass --bse-code" % (c[0], c[2], symbol)
    if len(exact) > 1 or len(cands) > 1:
        return None, "several BSE matches (%s): pass --bse-code" % ", ".join(
            "%s %s" % (c[0], c[2] or c[1]) for c in (exact or cands)[:5])
    return None, "no BSE match for %s: pass --bse-code" % symbol


def parse_bse(data):
    rows = []
    if isinstance(data, dict):
        rows = data.get("Table") or data.get("data") or []
    elif isinstance(data, list):
        rows = data
    out = []
    for r in rows:
        when = parse_date(pick(r, "NEWS_DT", "DissemDT", "DT_TM", "News_submission_dt"))
        head = pick(r, "HEADLINE", "NEWSSUB", default="")
        more = pick(r, "MORE", "NEWSSUB", "SLONGNAME", default="")
        att = str(pick(r, "ATTACHMENTNAME", default="") or "").strip()
        url = BSE_FILES + att if att and not att.startswith("http") else att
        cat = clean(pick(r, "CATEGORYNAME", default=""))
        sub = clean(pick(r, "SUBCATNAME", default=""))
        tag = " / ".join(x for x in (cat, sub) if x)
        it = make_item("BSE", "announcement", when, head, ("[%s] " % tag if tag else "") + clean(more) if more != head else tag, url)
        out.append(it)
    return out


def collect_bse(f, symbol, since, until, code):
    notes = []
    if not code:
        code, note = find_bse_code(f, symbol)
        notes.append(note)
        if not code:
            raise ResearchError(note)
    f.warm("bse", "https://www.bseindia.com/", bse_headers())
    url = (BSE_API + "AnnSubCategoryGetData/w?pageno=1&strCat=-1&strPrevDate=%s&strScrip=%s&strSearch=P"
           "&strToDate=%s&strType=C" % (since.strftime("%Y%m%d"), code, until.strftime("%Y%m%d")))
    data = f.json(url, bse_headers(), "bse-announcements.json")
    items = parse_bse(data)
    if not items:
        notes.append("BSE returned no announcements for code %s in this window" % code)
    return items, notes


# ---------------------------------------------------------------- Yahoo

def yahoo_crumb(f):
    """Cookie then crumb. Returns crumb or raises."""
    f.warm("yahoo", "https://fc.yahoo.com/")
    crumb = f.get("https://query1.finance.yahoo.com/v1/test/getcrumb", {"Accept": "text/plain"}).decode().strip()
    if not crumb or "<" in crumb or len(crumb) > 40:
        raise ResearchError("Yahoo did not give a crumb (blocked or changed)")
    return crumb


def cr(v):
    """Rupees -> Rs crore."""
    return None if v is None else v / 1e7


def raw(v):
    return v.get("raw") if isinstance(v, dict) else v


def parse_yahoo_summary(data):
    res = (((data or {}).get("quoteSummary") or {}).get("result") or [None])[0]
    if not res:
        err = ((data or {}).get("quoteSummary") or {}).get("error")
        raise ResearchError("Yahoo has no statements for this symbol" + (": %s" % clean(err) if err else ""))
    out = {"annual": [], "quarterly": [], "calendar": [], "profile": {}}
    for key, dest in (("incomeStatementHistory", "annual"), ("incomeStatementHistoryQuarterly", "quarterly")):
        block = res.get(key) or {}
        for r in block.get("incomeStatementHistory") or []:
            end = raw(r.get("endDate"))
            rev, ni = raw(r.get("totalRevenue")), raw(r.get("netIncome"))
            op, ebit = raw(r.get("operatingIncome")), raw(r.get("ebit"))
            out[dest].append({"period_end": ts_to_local(end).date().isoformat() if end else None,
                              "revenue_cr": cr(rev), "operating_income_cr": cr(op if op is not None else ebit),
                              "net_income_cr": cr(ni)})
    cal = (res.get("calendarEvents") or {}).get("earnings") or {}
    for d in cal.get("earningsDate") or []:
        ts = raw(d)
        if ts:
            out["calendar"].append(ts_to_local(ts).date().isoformat())
    prof = res.get("assetProfile") or {}
    out["profile"] = {"sector": prof.get("sector"), "industry": prof.get("industry"),
                      "employees": prof.get("fullTimeEmployees")}
    return out


def parse_yahoo_chart(data):
    r = (((data or {}).get("chart") or {}).get("result") or [None])[0]
    if not r:
        raise ResearchError("Yahoo has no price data for this symbol")
    m = r.get("meta") or {}
    ts = m.get("regularMarketTime")
    return {"name": m.get("longName") or m.get("shortName"), "price": m.get("regularMarketPrice"),
            "previous_close": m.get("chartPreviousClose") or m.get("previousClose"),
            "high_52w": m.get("fiftyTwoWeekHigh"), "low_52w": m.get("fiftyTwoWeekLow"),
            "day_high": m.get("regularMarketDayHigh"), "day_low": m.get("regularMarketDayLow"),
            "volume": m.get("regularMarketVolume"),
            "as_of": ts_to_local(ts).isoformat() if ts else None}


def collect_yahoo(f, symbol):
    """Returns (data dict, notes). Price and statements are separate; either may fail."""
    notes, out = [], {"quote": None, "statements": None}
    q = yahoo_q(symbol)
    try:
        out["quote"] = parse_yahoo_chart(f.json(
            "https://query2.finance.yahoo.com/v8/finance/chart/%s?range=1y&interval=1d" % q, None, "yahoo-chart.json"))
    except ResearchError as e:
        notes.append("price: %s" % e)
    try:
        crumb = urllib.parse.quote(yahoo_crumb(f), safe="") if f.offline is None else ""
        url = ("https://query2.finance.yahoo.com/v10/finance/quoteSummary/%s?modules="
               "incomeStatementHistory,incomeStatementHistoryQuarterly,calendarEvents,assetProfile%s"
               % (q, "&crumb=" + crumb if crumb else ""))
        out["statements"] = parse_yahoo_summary(f.json(url, None, "yahoo-summary.json"))
    except ResearchError as e:
        notes.append("statements: %s" % e)
    if out["quote"] is None and out["statements"] is None:
        raise ResearchError("; ".join(notes))
    return out, notes


# ---------------------------------------------------------------- Screener

class _TableGrabber(HTMLParser):
    """Collects <section id=X> tables as lists of rows of cell text."""

    def __init__(self, wanted):
        super().__init__(convert_charrefs=True)
        self.wanted = set(wanted)
        self.sec = None
        self.depth = 0
        self.rows = {}
        self.row = None
        self.cell = None
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "section":
            if self.sec is not None:
                self.depth += 1
            elif a.get("id") in self.wanted:
                self.sec, self.depth = a["id"], 0
                self.rows.setdefault(self.sec, [])
        elif tag == "title":
            self._in_title = True
        if self.sec is None:
            return
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if self.sec is None:
            return
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows[self.sec].append(self.row)
            self.row = None
        elif tag == "section":
            if self.depth == 0:
                self.sec = None
            else:
                self.depth -= 1

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self.cell is not None:
            self.cell.append(data)


def _label(cell):
    return re.sub(r"[\s +]+$", "", re.sub(r"^[\s +]+", "", cell)).rstrip("+ ").strip()


def table_series(rows):
    """First row = period headers. Returns (periods, {label: [values]})."""
    if not rows:
        return [], {}
    periods = rows[0][1:]
    series = {}
    for r in rows[1:]:
        if not r or not _label(r[0]):
            continue
        vals = [num(x) for x in r[1:1 + len(periods)]]
        vals += [None] * (len(periods) - len(vals))
        series[_label(r[0])] = vals
    return periods, series


def pct_change(new, old):
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old) * 100.0


def summarize_table(rows, lag, wanted):
    """Latest column against `lag` columns earlier (4 quarters back, or 1 year back)."""
    periods, series = table_series(rows)
    # Screener may add a trailing TTM column to the annual table: ignore it for the year-on-year step.
    keep = [i for i, p in enumerate(periods) if p and p.upper() != "TTM"]
    periods_k = [periods[i] for i in keep]
    out = {"periods": periods_k[-8:], "rows": {}, "latest": periods_k[-1] if periods_k else None}
    for want in wanted:
        key = next((k for k in series if k.lower().startswith(want.lower())), None)
        if not key:
            continue
        vals = [series[key][i] for i in keep]
        last = vals[-1] if vals else None
        prev = vals[-1 - lag] if len(vals) > lag else None
        out["rows"][key] = {"values": vals[-8:], "latest": last, "year_ago": prev,
                            "change_pct": pct_change(last, prev) if "%" not in key else None}
    return out


def parse_screener(text):
    p = _TableGrabber(["quarters", "profit-loss", "shareholding", "top-ratios"])
    p.feed(text)
    name = re.sub(r"\s*(?:share price|stock price|[-|]).*$", "", clean(p.title), flags=re.I)
    out = {"name": name or None, "quarterly": None, "annual": None, "holding": None}
    wq = ["Sales", "Revenue", "Expenses", "Operating Profit", "OPM %", "Other Income", "Profit before tax",
          "Net Profit", "EPS in Rs"]
    if p.rows.get("quarters"):
        out["quarterly"] = summarize_table(p.rows["quarters"], 4, wq)
    if p.rows.get("profit-loss"):
        out["annual"] = summarize_table(p.rows["profit-loss"], 1, wq + ["Dividend Payout %"])
    if p.rows.get("shareholding"):
        periods, series = table_series(p.rows["shareholding"])
        out["holding"] = {"periods": periods[-4:], "rows": {k: v[-4:] for k, v in series.items()}}
    m = re.search(r"([A-Za-z ]*Results[^<]{0,80}|Concall[^<]{0,80})", text)
    if not out["quarterly"] and not out["annual"]:
        raise ResearchError("the page had no quarterly or profit-and-loss table (not logged in, a new layout, "
                            "or a block page)")
    return out


def collect_screener(f, symbol):
    q = urllib.parse.quote(symbol, safe="")
    last = None
    for suffix, saved in (("consolidated/", "screener.html"), ("", "screener.html")):
        try:
            text = f.get("https://www.screener.in/company/%s/%s" % (q, suffix), {"Accept": "text/html"}, saved).decode(
                "utf-8", "replace")
            data = parse_screener(text)
            data["url"] = "https://www.screener.in/company/%s/%s" % (q, suffix)
            data["basis"] = "consolidated" if suffix else "standalone"
            return data
        except ResearchError as e:
            last = e
            if f.offline is not None:
                break
    raise last


# ---------------------------------------------------------------- Google News

def parse_google(data, symbol, name=None):
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ResearchError("Google News did not return RSS (%s)" % e)
    out = []
    for it in root.iter("item"):
        title = clean(it.findtext("title"))
        src = clean(it.findtext("source"))
        if src and title.endswith(" - " + src):
            title = title[:-(len(src) + 3)]
        out.append(make_item("Google News" + (" / " + src if src else ""), "news", parse_date(it.findtext("pubDate")),
                             title, "", (it.findtext("link") or "").strip()))
    return out


def collect_google(f, symbol, name, days):
    terms = '"%s"' % (name or symbol)
    q = "%s (NSE OR BSE OR shares OR results OR stock) when:%dd" % (terms, min(max(days, 1), 365))
    url = "https://news.google.com/rss/search?q=%s&hl=en-IN&gl=IN&ceid=IN:en" % urllib.parse.quote(q)
    return parse_google(f.get(url, {"Accept": "application/rss+xml"}, "google-news.xml"), symbol, name)


# ---------------------------------------------------------------- assemble

def dedupe(items):
    seen, out = set(), []
    for it in sorted(items, key=lambda i: i["when"] or "", reverse=True):
        key = (re.sub(r"\W+", "", it["title"].lower())[:70], (it["when"] or "")[:10])
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def research(symbol, f, now, days=90, sources=ALL_SOURCES, bse_code=None, name=None):
    """Runs every chosen source; returns the report dict. Never raises for a source failure."""
    since = now - _dt.timedelta(days=days)
    rep = {"symbol": symbol, "as_of": now.isoformat(), "days": days, "name": name, "sources": {}, "items": [],
           "financials": {}, "market": None, "upcoming": []}
    items = []

    def run(src, fn):
        try:
            res = fn()
            rep["sources"][src] = {"status": "ok"}
            return res
        except ResearchError as e:
            rep["sources"][src] = {"status": "failed", "reason": str(e)}
        except Exception as e:  # a changed page layout must not take the others down
            rep["sources"][src] = {"status": "failed", "reason": "unexpected %s: %s" % (type(e).__name__, e)}
        return None

    if "screener" in sources:
        d = run("screener", lambda: collect_screener(f, symbol))
        if d:
            rep["financials"]["screener"] = d
            rep["name"] = rep["name"] or d.get("name")
    if "yahoo" in sources:
        got = run("yahoo", lambda: collect_yahoo(f, symbol))
        if got:
            data, notes = got
            rep["market"] = data["quote"]
            if data["statements"]:
                rep["financials"]["yahoo"] = data["statements"]
                for d in data["statements"].get("calendar", []):
                    rep["upcoming"].append({"source": "Yahoo", "date": d, "what": "earnings date (estimate)"})
            if data["quote"] and data["quote"].get("name"):
                rep["name"] = rep["name"] or data["quote"]["name"]
            if notes:
                rep["sources"]["yahoo"]["notes"] = notes
    if "nse" in sources:
        got = run("nse", lambda: _need_some(collect_nse(f, symbol, since, now)))
        if got:
            its, notes, ok, tried = got
            items += its
            rep["sources"]["nse"].update({"notes": notes, "endpoints_ok": ok, "endpoints_tried": tried})
            if ok < tried:
                rep["sources"]["nse"]["status"] = "partial"
    if "bse" in sources:
        got = run("bse", lambda: collect_bse(f, symbol, since, now, bse_code))
        if got:
            its, notes = got
            items += its
            if notes:
                rep["sources"]["bse"]["notes"] = notes
    if "google" in sources:
        its = run("google", lambda: collect_google(f, symbol, rep["name"], days))
        if its:
            items += its

    cutoff = since
    kept = []
    for it in items:
        d = _dt.datetime.fromisoformat(it["when"]) if it["when"] else None
        if it["kind"] in ("action", "board") or d is None or d >= cutoff:
            kept.append(it)  # actions and meetings can lie in the future or a bit back: keep them
    rep["items"] = dedupe(kept)

    for it in rep["items"]:  # future-dated board meetings and record dates
        d = _dt.datetime.fromisoformat(it["when"]) if it["when"] else None
        if d and d.date() >= now.date() and it["kind"] in ("board", "action"):
            rep["upcoming"].append({"source": it["source"], "date": d.date().isoformat(), "what": it["title"]})

    for src, info in rep["sources"].items():  # staleness per source
        dates = [it["when"] for it in rep["items"] if it["source"].startswith({"nse": "NSE", "bse": "BSE",
                                                                              "google": "Google"}.get(src, "?"))
                 and it["when"] and it["kind"] not in ("action", "board")]
        if dates:
            newest = _dt.datetime.fromisoformat(max(dates))
            info["newest"] = newest.isoformat()
            if (now - newest).days > STALE_DAYS:
                info["stale"] = True
    return rep


def _need_some(res):
    items, notes, ok, tried = res
    if ok == 0:
        raise ResearchError("every NSE endpoint failed: " + "; ".join(notes[:3]) +
                            (" ..." if len(notes) > 3 else "") +
                            ". NSE blocks scripts often: use BSE, or open nseindia.com in a browser")
    return res


# ---------------------------------------------------------------- render

def fmt_val(v, pct=False):
    if v is None:
        return "n/a"
    return ("%.1f%%" % v) if pct else "{:,.2f}".format(v)


def render_table(block, title, label_hint):
    if not block or not block.get("rows"):
        return []
    lines = ["  %s (Rs Cr, as shown by Screener; latest %s)" % (title, block["latest"])]
    per = block["periods"]
    lines.append("    %-18s" % "" + "".join("%10s" % p for p in per[-5:]) + "   %s" % label_hint)
    for key, r in block["rows"].items():
        pct = "%" in key
        vals = r["values"][-5:]
        pad = [None] * (len(per[-5:]) - len(vals)) + vals
        chg = "" if r["change_pct"] is None else "%+.1f%%" % r["change_pct"]
        lines.append("    %-18s" % key[:18] + "".join("%10s" % fmt_val(v, pct) for v in pad) + "   %s" % chg)
    return lines


def render(rep, show=8):
    L = []
    title = "%s%s" % (rep["symbol"], " - " + rep["name"] if rep["name"] else "")
    L.append("RESEARCH: %s   as of %s IST   (last %d days)" % (title, rep["as_of"].replace("T", " ")[:16], rep["days"]))
    L.append("Sources are free, unofficial and can lag or block. Nothing here is advice or a forecast.")
    L.append("")
    L.append("SOURCES")
    for src in ALL_SOURCES:
        s = rep["sources"].get(src)
        if not s:
            continue
        line = "  %-9s %s" % (src, s["status"].upper())
        if s["status"] == "failed":
            line += ": " + s["reason"]
        if s.get("endpoints_tried"):
            line += " (%d of %d NSE endpoints answered)" % (s["endpoints_ok"], s["endpoints_tried"])
        if s.get("stale"):
            line += "  STALE: newest item is %s" % fmt_dt(_dt.datetime.fromisoformat(s["newest"]))
        L.append(line)
        for n in s.get("notes", []):
            L.append("            - " + n)
    L.append("")

    m = rep.get("market")
    if m:
        L.append("PRICE (Yahoo, %s IST)" % (m["as_of"] or "time unknown").replace("T", " ")[:16])
        bits = []
        if m.get("price") is not None:
            bits.append("last Rs %s" % money(m["price"]))
        if m.get("price") is not None and m.get("previous_close"):
            bits.append("%+.2f%% on previous close" % pct_change(m["price"], m["previous_close"]))
        if m.get("low_52w") is not None and m.get("high_52w") is not None:
            bits.append("52-week range Rs %s to %s" % (money(m["low_52w"]), money(m["high_52w"])))
        L.append("  " + "; ".join(bits))
        L.append("")

    fin = rep["financials"]
    sc = fin.get("screener")
    if sc:
        L.append("FINANCIALS (screener.in, %s; Rs crore)" % sc.get("basis", ""))
        L += render_table(sc.get("quarterly"), "Quarterly", "change vs 4 quarters ago")
        L += render_table(sc.get("annual"), "Profit and loss, annual", "change vs previous year")
        h = sc.get("holding")
        if h and h.get("rows"):
            L.append("  Shareholding %% (%s)" % ", ".join(h["periods"]))
            for k, v in h["rows"].items():
                L.append("    %-14s %s" % (k[:14], "  ".join(fmt_val(x, True) for x in v)))
        L.append("")
    y = fin.get("yahoo")
    if y and (y["quarterly"] or y["annual"]):
        L.append("INCOME STATEMENTS (Yahoo, Rs crore)")
        for kind, rows in (("Quarterly", y["quarterly"]), ("Annual", y["annual"])):
            for r in rows[:4]:
                L.append("  %-9s %s  revenue %s  net income %s" % (kind, r["period_end"],
                                                                  fmt_val(r["revenue_cr"]), fmt_val(r["net_income_cr"])))
        L.append("")
    if not sc and not (y and (y["quarterly"] or y["annual"])):
        res = [i for i in rep["items"] if i["kind"] == "result"]
        if not res:
            L.append("FINANCIALS: no data from any source (see SOURCES). Open screener.in or the company's")
            L.append("  results page on nseindia.com / bseindia.com for the numbers.")
            L.append("")

    if rep["upcoming"]:
        L.append("COMING UP")
        for u in sorted(rep["upcoming"], key=lambda x: x["date"]):
            L.append("  %s  %s  (%s)" % (u["date"], clean(u["what"]), u["source"]))
        L.append("")

    by = {}
    for it in rep["items"]:
        by.setdefault(it["topic"], []).append(it)
    for t in TOPIC_ORDER:
        rows = by.get(t)
        if not rows:
            continue
        L.append("%s  [%d]" % (TOPIC_TITLES[t].upper(), len(rows)))
        for it in rows[:show]:
            when = fmt_dt(_dt.datetime.fromisoformat(it["when"])) if it["when"] else "no date"
            L.append("  %-22s %s" % (when, it["title"][:150]))
            if it.get("detail"):
                L.append("  %-22s %s" % ("", it["detail"][:170]))
            L.append("  %-22s [%s]%s" % ("", it["source"], " " + it["url"] if it["url"] else ""))
        if len(rows) > show:
            L.append("  ... %d more (--show N, or the JSON file)" % (len(rows) - show))
        L.append("")
    if not rep["items"]:
        L.append("No announcements or news came back from any source in this window.")
        L.append("")
    L.append("Check each item at its source before you act. Dates are IST. Not investment advice.")
    return "\n".join(L)


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description="Research one NSE stock from NSE, BSE, Yahoo, Screener and Google News.")
    ap.add_argument("symbol", help="NSE symbol, e.g. RELIANCE, M&M, BAJAJ-AUTO")
    ap.add_argument("--days", type=int, default=90, help="how far back for announcements, deals and news (default 90)")
    ap.add_argument("--sources", default=",".join(ALL_SOURCES), help="comma list of: " + ", ".join(ALL_SOURCES))
    ap.add_argument("--bse-code", help="BSE scrip code (six digits) if the lookup cannot find it")
    ap.add_argument("--name", help="company name for the news search (default: from Yahoo or Screener)")
    ap.add_argument("--show", type=int, default=8, help="items per topic to print (default 8)")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    ap.add_argument("--no-write", action="store_true", help="do not write trader/research_<SYMBOL>.json")
    ap.add_argument("--offline", metavar="DIR", help="read saved files from DIR instead of the network")
    ap.add_argument("--now", help='pin the clock, IST: "YYYY-MM-DD HH:MM"')
    ap.add_argument("--out-dir", default="trader", help="where the JSON file goes (default trader)")
    ap.add_argument("--timeout", type=int, default=TIMEOUT)
    a = ap.parse_args(argv)
    try:
        symbol = normalize(a.symbol)
        if a.days < 1 or a.days > 3650:
            raise ResearchError("--days must be between 1 and 3650")
        srcs = [s.strip().lower() for s in a.sources.split(",") if s.strip()]
        bad = [s for s in srcs if s not in ALL_SOURCES]
        if bad or not srcs:
            raise ResearchError("unknown source %s; choose from %s" % (", ".join(bad) or "(none)", ", ".join(ALL_SOURCES)))
        if a.bse_code and not re.fullmatch(r"\d{5,6}", a.bse_code):
            raise ResearchError("--bse-code is the 5 or 6 digit number, like 500325")
        now = parse_now(a.now) if a.now else now_ist()
        if a.offline and not os.path.isdir(a.offline):
            raise ResearchError("--offline folder not found: %s" % a.offline)
    except ResearchError as e:
        print("research.py: %s" % e, file=sys.stderr)
        return 2
    f = Fetcher(a.offline, a.timeout)
    rep = research(symbol, f, now, a.days, srcs, a.bse_code, a.name)
    if not a.no_write:
        try:
            os.makedirs(a.out_dir, exist_ok=True)
            path = os.path.join(a.out_dir, "research_%s.json" % file_safe(symbol))
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(rep, fh, indent=2, ensure_ascii=False)
            rep["file"] = path
        except OSError as e:
            print("research.py: could not write the file (%s)" % e, file=sys.stderr)
    if a.json:
        print(json.dumps(rep, indent=2, ensure_ascii=False))
    else:
        print(render(rep, a.show))
        if rep.get("file"):
            print("Saved: %s" % rep["file"])
    ok = [s for s in rep["sources"].values() if s["status"] in ("ok", "partial")]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
