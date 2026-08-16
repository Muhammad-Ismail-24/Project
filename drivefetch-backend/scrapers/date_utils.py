"""
scrapers/date_utils.py

Single source of truth for listing-age parsing across every platform.

WHY THIS MODULE EXISTS (2026-08-16)
-----------------------------------
Every scraper carried its own copy of `_time_str_to_days()`, and each one
returned the magic number 999 when it could not find a date. Both normalisers
then treated 999 — and, crucially, *anything above 998* — as "age unknown"
and awarded a neutral score.

That sentinel collides with reality. A listing posted on Jul 19, 2022 is 1489
days old. 1489 > 998, so a genuinely ancient (and long-sold) advert was
classified as "age unknown", skipped the staleness veto, and scored a neutral
+10 — while a merely 6-month-old listing at 180 days was correctly vetoed.

Net effect: the older an advert got, the better it scored, as soon as it
crossed the 998-day line. Gari.pk surfaced Suzuki Every ads from July 2022
and May 2023 as if they were fresh inventory.

THE FIX
-------
UNKNOWN_AGE = -1. Real ages are always >= 0, so `age_days < 0` is the one and
only test for "we could not determine this listing's age". No real age can
ever masquerade as unknown, and no unknown can ever masquerade as fresh.
"""
import datetime
import re

# ---------------------------------------------------------------------------
# SENTINEL
# ---------------------------------------------------------------------------

# "We could not determine this listing's age."
# Negative by design: a real age is never negative, so this can never collide
# with a genuine value the way the old 999 sentinel did.
UNKNOWN_AGE = -1

# Platforms that always publish a posting date. If we come back with
# UNKNOWN_AGE for one of these, our parser broke — the listing is not merely
# undated, it is unverifiable, and it must not outrank a dated listing.
DATE_MANDATORY_PLATFORMS = {
    "gari.pk",
    "pakwheels",
    "olx",
    "wisewheels",
}

# A parsed date before this is almost certainly a misparse (a model year, a
# registration year, a phone number fragment) rather than a posting date.
_EARLIEST_PLAUSIBLE_YEAR = 2005

# Site clocks run ahead of ours sometimes; tolerate a small future skew and
# treat it as "posted today" rather than throwing the date away.
_MAX_FUTURE_SKEW_DAYS = 3

MONTH_MAP = {
    'jan': 1, 'january': 1,
    'feb': 2, 'february': 2,
    'mar': 3, 'march': 3,
    'apr': 4, 'april': 4,
    'may': 5,
    'jun': 6, 'june': 6,
    'jul': 7, 'july': 7,
    'aug': 8, 'august': 8,
    'sep': 9, 'sept': 9, 'september': 9,
    'oct': 10, 'october': 10,
    'nov': 11, 'november': 11,
    'dec': 12, 'december': 12,
}

_MONTH_ALT = '|'.join(sorted(MONTH_MAP, key=len, reverse=True))

# "Jul 19, 2022" / "May 2 2023" / "August 10, 2026"
_MDY_RE = re.compile(
    rf'\b({_MONTH_ALT})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b',
    re.I,
)
# "19 Jul 2022" / "2 May, 2023"
_DMY_RE = re.compile(
    rf'\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH_ALT})\.?,?\s+(\d{{4}})\b',
    re.I,
)
# "2022-07-19"
_ISO_RE = re.compile(r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b')
# "19-07-2022" / "19/07/2022"
_DMY_NUM_RE = re.compile(r'\b(\d{1,2})[-/](\d{1,2})[-/](\d{4})\b')

# Any absolute date shape — used to pre-screen text before a full parse.
ABSOLUTE_DATE_RE = re.compile(
    rf'\b(?:{_MONTH_ALT})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}'
    rf'|\b\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTH_ALT})\.?,?\s+\d{{4}}'
    r'|\b\d{4}-\d{1,2}-\d{1,2}\b'
    r'|\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b',
    re.I,
)

# "3 days ago", "about 2 weeks ago", "1 month", "10 hours ago"
_RELATIVE_RE = re.compile(
    r'(?:about\s+)?(\d+)\s*(minute|min|hour|hr|day|week|month|year)s?\b',
    re.I,
)
_RELATIVE_UNIT_DAYS = {
    'minute': 0, 'min': 0, 'hour': 0, 'hr': 0,
    'day': 1, 'week': 7, 'month': 30, 'year': 365,
}

# Same-day / next-day phrasing, English and Urdu.
_TODAY_RE = re.compile(
    r'\b(?:just\s*now|today|moments?\s*ago|few\s*(?:seconds|minutes)\s*ago)\b'
    r'|ابھی|گھنٹ|منٹ',
    re.I,
)
_YESTERDAY_RE = re.compile(r'\byesterday\b|\bکل\b', re.I)

# Urdu relative units.
_URDU_UNITS = (
    (re.compile(r'(\d+)\s*دن'), 1),
    (re.compile(r'(\d+)\s*ہفتے'), 7),
    (re.compile(r'(\d+)\s*مہینے'), 30),
    (re.compile(r'(\d+)\s*سال'), 365),
)


# ---------------------------------------------------------------------------
# CORE HELPERS
# ---------------------------------------------------------------------------

def is_unknown_age(age_days) -> bool:
    """True when the age could not be determined. The only correct test."""
    return age_days is None or age_days < 0


def days_since(posted: datetime.date, today: datetime.date = None) -> int:
    """
    Days between `posted` and today, floored at 0.

    A date up to _MAX_FUTURE_SKEW_DAYS in the future is clamped to 0 (site
    clock skew). Anything further into the future is rejected by the callers
    that validate the date first.
    """
    today = today or datetime.date.today()
    return max(0, (today - posted).days)


def _valid_date(year: int, month: int, day: int,
                today: datetime.date = None) -> datetime.date | None:
    """Builds a date and rejects anything outside the plausible posting window."""
    today = today or datetime.date.today()
    if year < _EARLIEST_PLAUSIBLE_YEAR:
        return None
    try:
        parsed = datetime.date(year, month, day)
    except ValueError:
        return None
    if (parsed - today).days > _MAX_FUTURE_SKEW_DAYS:
        return None
    return parsed


def parse_absolute_date(text: str,
                        today: datetime.date = None) -> datetime.date | None:
    """
    Extracts an absolute posting date from free text.

    Handles the four shapes Pakistani car portals actually emit:
      "Jul 19, 2022" | "19 Jul 2022" | "2022-07-19" | "19-07-2022"

    Returns None when no plausible date is present. Unlike the old
    strptime-in-a-try/except approach, a bogus month token ("VXR 2 2015")
    fails the MONTH_MAP lookup instead of raising, so control flow stays
    explicit.
    """
    if not text:
        return None
    today = today or datetime.date.today()

    m = _MDY_RE.search(text)
    if m:
        month = MONTH_MAP.get(m.group(1).lower())
        if month:
            parsed = _valid_date(int(m.group(3)), month, int(m.group(2)), today)
            if parsed:
                return parsed

    m = _DMY_RE.search(text)
    if m:
        month = MONTH_MAP.get(m.group(2).lower())
        if month:
            parsed = _valid_date(int(m.group(3)), month, int(m.group(1)), today)
            if parsed:
                return parsed

    m = _ISO_RE.search(text)
    if m:
        parsed = _valid_date(int(m.group(1)), int(m.group(2)), int(m.group(3)), today)
        if parsed:
            return parsed

    m = _DMY_NUM_RE.search(text)
    if m:
        # Day-first: Pakistani portals never use US month-first numeric dates.
        parsed = _valid_date(int(m.group(3)), int(m.group(2)), int(m.group(1)), today)
        if parsed:
            return parsed

    return None


def age_days_from_text(text: str, today: datetime.date = None) -> int:
    """
    Converts a date or relative-time string into an age in days.

    Absolute dates win over relative phrasing — they are exact, and a card
    that shows both ("Posted Jul 19, 2022 · updated 2 days ago") should be
    judged on when it was posted.

    Returns UNKNOWN_AGE (-1) when nothing parseable is present. Callers must
    test with is_unknown_age(), never against a magic number.
    """
    if not text:
        return UNKNOWN_AGE
    today = today or datetime.date.today()

    posted = parse_absolute_date(text, today)
    if posted:
        return days_since(posted, today)

    lowered = text.lower()

    m = _RELATIVE_RE.search(lowered)
    if m:
        multiplier = _RELATIVE_UNIT_DAYS[m.group(2).lower()]
        return int(m.group(1)) * multiplier

    for pattern, multiplier in _URDU_UNITS:
        m = pattern.search(text)
        if m:
            return int(m.group(1)) * multiplier

    if _TODAY_RE.search(text):
        return 0
    if _YESTERDAY_RE.search(text):
        return 1

    return UNKNOWN_AGE


# Text that plausibly IS a posting date, as opposed to text that merely
# contains digits. Requires either an explicit relative phrase or a real month
# token, so a headline like "Suzuki Alto VXR 2 2015" cannot register as a date.
_CARD_DATE_HINT_RE = re.compile(
    r'\b\d+\s*(?:minute|min|hour|hr|day|week|month|year)s?\s*(?:ago|old|back)\b'
    r'|\bjust\s*now\b|\btoday\b|\byesterday\b'
    rf'|{ABSOLUTE_DATE_RE.pattern}',
    re.I,
)


def age_days_from_card(item, max_text_len: int = 80,
                       today: datetime.date = None) -> int:
    """
    Best-effort age extraction from an arbitrary listing card element.

    Used by the scrapers that have no dedicated date cell to target. The scan
    is deliberately conservative:

      1. A <time datetime="..."> attribute, if present.
      2. An element whose class or data attribute names it as a date carrier.
      3. Short text nodes that match _CARD_DATE_HINT_RE — which demands a real
         month name or an explicit relative phrase, so mileage ("45,000 km"),
         engine size ("660 cc") and model years ("2015") cannot be misread as
         posting dates.

    Returns UNKNOWN_AGE when the card carries no readable date.
    """
    today = today or datetime.date.today()

    time_tag = item.find('time')
    if time_tag:
        age = age_days_from_timestamp(time_tag.get('datetime', ''), today)
        if not is_unknown_age(age):
            return age
        age = age_days_from_text(time_tag.get_text(strip=True), today)
        if not is_unknown_age(age):
            return age

    labelled = item.find(class_=re.compile(
        r'(posted|listing.?date|date.?added|\bdate\b|\bago\b|timeago)', re.I
    ))
    if labelled:
        age = age_days_from_text(labelled.get_text(strip=True), today)
        if not is_unknown_age(age):
            return age

    for el in item.find_all(['span', 'small', 'p', 'div', 'li', 'td', 'label']):
        text = el.get_text(strip=True)
        if not text or len(text) > max_text_len:
            continue
        if not _CARD_DATE_HINT_RE.search(text):
            continue
        age = age_days_from_text(text, today)
        if not is_unknown_age(age):
            return age

    return UNKNOWN_AGE


def age_days_from_timestamp(value, today: datetime.date = None) -> int:
    """
    Converts a unix epoch or ISO-8601 timestamp into an age in days.

    Used by the JSON-API scrapers (OLX `createdAt`, WiseWheels `created_at`).
    Returns UNKNOWN_AGE on anything unparseable.
    """
    if value in (None, "", 0):
        return UNKNOWN_AGE
    today = today or datetime.date.today()

    # Unix epoch seconds
    try:
        return days_since(
            datetime.datetime.fromtimestamp(
                int(value), tz=datetime.timezone.utc
            ).date(),
            today,
        )
    except (TypeError, ValueError, OSError, OverflowError):
        pass

    # ISO-8601, with or without a trailing Z
    try:
        return days_since(
            datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00")).date(),
            today,
        )
    except (TypeError, ValueError):
        pass

    return UNKNOWN_AGE
