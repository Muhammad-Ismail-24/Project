"""
test_staleness_veto.py

Regression tests for the 2026-08-16 staleness-veto bypass.

THE BUG
-------
`999` was the "age unknown" sentinel. Both normalisers exempted it with an
upper-bound test — `age_days > 998` in normalizer.py, `age_days <= 998` in
recommend_normalizer.py — and those tests also matched every REAL age above
998 days. A Gari.pk Suzuki Every posted Jul 19, 2022 is 1489 days old, so it
was classified "age unknown", awarded a neutral score, and never reached the
staleness veto. A 969-day listing from Dec 2023 was correctly vetoed.

Result: adverts older than roughly 2.7 years outranked adverts half their age.

Run:  python test_staleness_veto.py
"""
import datetime
import sys

from models.car_schema import CarListing
from scrapers.date_utils import (
    UNKNOWN_AGE,
    age_days_from_text,
    is_unknown_age,
    parse_absolute_date,
)
from scrapers.gari_pk import parse_detail_age_days, parse_gari_cards
from scrapers.normalizer import _calculate_relevance_score
from scrapers.recommend_normalizer import _score_listing

TODAY = datetime.date.today()

_passed = 0
_failed = 0


def check(label: str, actual, expected):
    global _passed, _failed
    if actual == expected:
        _passed += 1
        print(f"  PASS  {label}: {actual}")
    else:
        _failed += 1
        print(f"  FAIL  {label}: got {actual!r}, expected {expected!r}")


def check_true(label: str, condition, detail=""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  PASS  {label}{(' — ' + str(detail)) if detail else ''}")
    else:
        _failed += 1
        print(f"  FAIL  {label}{(' — ' + str(detail)) if detail else ''}")


def days_ago(n: int) -> str:
    """The 'Mmm DD, YYYY' string for a date n days before today."""
    return (TODAY - datetime.timedelta(days=n)).strftime("%b %-d, %Y") \
        if sys.platform != "win32" \
        else (TODAY - datetime.timedelta(days=n)).strftime("%b %#d, %Y")


def make_car(age_days: int, platform: str = "Gari.pk") -> CarListing:
    return CarListing(
        title="Suzuki Every Join 2016 for Sale",
        price="PKR 20.9 Lacs",
        mileage="33000",
        city="Islamabad",
        year="2016",
        listing_url="https://www.gari.pk/used-cars/suzuki-every-2016-x/",
        platform=platform,
        age_days=age_days,
    )


def score_search(car: CarListing) -> float:
    return _calculate_relevance_score(
        car=car,
        requested_make="Suzuki",
        requested_model="Every",
        requested_city="Islamabad",
        requested_budget=0,
        requested_color=None,
        clean_price=2090000,
        clean_year=2016,
        clean_mileage=33000,
    )


def score_recommend(car: CarListing) -> float:
    return _score_listing(
        car=car,
        requested_make="Suzuki",
        requested_model="Every",
        requested_city="Islamabad",
        requested_budget=0,
        requested_color="",
        clean_price=2090000,
        clean_year=2016,
        clean_mileage=33000,
    )


# ---------------------------------------------------------------------------
print("\n[1] Date string parsing — the exact 'Date Posted' formats gari.pk emits")
# ---------------------------------------------------------------------------
check("Jul 19, 2022 parses",
      parse_absolute_date("Jul 19, 2022"), datetime.date(2022, 7, 19))
check("May 2, 2023 parses",
      parse_absolute_date("May 2, 2023"), datetime.date(2023, 5, 2))
check("Aug 10, 2026 parses",
      parse_absolute_date("Aug 10, 2026"), datetime.date(2026, 8, 10))
check("no-comma 'Apr 09 2026' parses (FameWheels form)",
      parse_absolute_date("Apr 09 2026"), datetime.date(2026, 4, 9))

check_true("Jul 19, 2022 age is 1400+ days",
           age_days_from_text("Jul 19, 2022") >= 1400,
           f"{age_days_from_text('Jul 19, 2022')} days")
check_true("May 23, 2023 age is 1100+ days",
           age_days_from_text("May 23, 2023") >= 1100,
           f"{age_days_from_text('May 23, 2023')} days")

check("'17 days ago' -> 17", age_days_from_text("17 days ago"), 17)
check("'10 hours ago' -> 0", age_days_from_text("10 hours ago"), 0)
check("'1 day ago' -> 1", age_days_from_text("1 day ago"), 1)

# A model-year token in a headline must never register as a posting date.
check("headline 'Suzuki Alto VXR 2 2015' -> unknown",
      age_days_from_text("Suzuki Alto VXR 2 2015"), UNKNOWN_AGE)
check("mileage '200000 km' -> unknown",
      age_days_from_text("200000 km"), UNKNOWN_AGE)
check("engine '660 cc' -> unknown", age_days_from_text("660 cc"), UNKNOWN_AGE)
check("empty cell '-' -> unknown", age_days_from_text("-"), UNKNOWN_AGE)

# ---------------------------------------------------------------------------
print("\n[2] Sentinel cannot collide with a real age")
# ---------------------------------------------------------------------------
check_true("UNKNOWN_AGE is negative", UNKNOWN_AGE < 0, UNKNOWN_AGE)
check_true("1489 is not unknown", not is_unknown_age(1489))
check_true("999 is not unknown", not is_unknown_age(999))
check_true("0 is not unknown (posted today)", not is_unknown_age(0))
check_true("UNKNOWN_AGE is unknown", is_unknown_age(UNKNOWN_AGE))

# ---------------------------------------------------------------------------
print("\n[3] Search normalizer — the reported regression")
# ---------------------------------------------------------------------------
jul_2022 = age_days_from_text("Jul 19, 2022")
may_2023 = age_days_from_text("May 23, 2023")

check("Jul 19 2022 listing (%d d) vetoed" % jul_2022,
      score_search(make_car(jul_2022)), 0.0)
check("May 23 2023 listing (%d d) vetoed" % may_2023,
      score_search(make_car(may_2023)), 0.0)
check("969-day listing still vetoed (was already correct)",
      score_search(make_car(969)), 0.0)
check("91-day listing vetoed (just over the limit)",
      score_search(make_car(91)), 0.0)

fresh = score_search(make_car(6))
check_true("6-day listing passes", fresh > 0.0, f"score {fresh}")
check_true("90-day listing passes (at the limit)",
           score_search(make_car(90)) > 0.0, f"score {score_search(make_car(90))}")
check_true("fresh outranks 90-day",
           fresh > score_search(make_car(90)),
           f"{fresh} > {score_search(make_car(90))}")

# 'Posted today' must beat 'age unknown', which the old `age_days == 0` branch
# prevented — both were flattened to the same neutral 10.0.
today_score = score_search(make_car(0))
unknown_gari = score_search(make_car(UNKNOWN_AGE, platform="Gari.pk"))
unknown_drive = score_search(make_car(UNKNOWN_AGE, platform="Drive.pk"))
check_true("posted-today beats unknown-age",
           today_score > unknown_gari,
           f"today {today_score} > unknown {unknown_gari}")
check_true("unknown age is not vetoed outright",
           unknown_drive > 0.0, f"score {unknown_drive}")
check_true("unknown on a date-mandatory platform scores below unknown elsewhere",
           unknown_gari < unknown_drive,
           f"Gari.pk {unknown_gari} < Drive.pk {unknown_drive}")

# ---------------------------------------------------------------------------
print("\n[4] Recommendation normalizer — same bypass, 60-day limit")
# ---------------------------------------------------------------------------
check("Jul 19 2022 listing vetoed", score_recommend(make_car(jul_2022)), 0.0)
check("May 23 2023 listing vetoed", score_recommend(make_car(may_2023)), 0.0)
check("1489-day listing vetoed", score_recommend(make_car(1489)), 0.0)
check("61-day listing vetoed (over the 60-day limit)",
      score_recommend(make_car(61)), 0.0)
rec_fresh = score_recommend(make_car(6))
check_true("6-day listing passes", rec_fresh > 0.0, f"score {rec_fresh}")
check_true("unknown age is not vetoed outright",
           score_recommend(make_car(UNKNOWN_AGE, platform="Drive.pk")) > 0.0)

# ---------------------------------------------------------------------------
print("\n[5] Gari.pk card parsing — real markup, both date forms")
# ---------------------------------------------------------------------------
CARD_TEMPLATE = """
<div class="fleft block_ss" id="cat-contents">
  <div class="fleft" id="image-cat"><span><a href="/used-cars/suzuki-every-2016-for-sale-in-islamabad-1/">
    <img alt="Suzuki Every 2016" src="https://www.gari.pk/images/ads/cars/thumbs/x.jpg"/></a></span></div>
  <div id="ad-desc">
    <div id="ad-title"><a href="/used-cars/suzuki-every-2016-for-sale-in-islamabad-1/">
      <h3 class="color-site"><span>{title}</span></h3></a></div>
    <div class="fleft" id="price-cat">
      <div class="div_feat">{year}</div>
      <div class="div_feat">Islamabad</div>
      <div class="div_feat">33000 km</div>
      <div class="div_feat"><div style="font-weight: bolder;">Rs. 20.9 Lacs</div></div>
      <div class="div_feat">Petrol</div>
      <div class="div_feat">660 cc</div>
      <div class="div_feat">Automatic</div>
      <div class="div_feat">{date_cell}</div>
    </div>
  </div>
</div>
"""

html = "".join([
    CARD_TEMPLATE.format(title="Suzuki Every 2016 for Sale", year="2016",
                         date_cell="Jul 19, 2022"),
    CARD_TEMPLATE.format(title="Suzuki Every 2014 for Sale", year="2014",
                         date_cell="May 23, 2023"),
    CARD_TEMPLATE.format(title="Suzuki Every Join 2014 for Sale", year="2014",
                         date_cell="1 day ago"),
    CARD_TEMPLATE.format(title="Suzuki Alto VXR 2 2015 for Sale", year="2015",
                         date_cell="-"),
])

cards = parse_gari_cards(html, searched_city="Islamabad")
check("4 cards parsed", len(cards), 4)
check_true("card 0 (Jul 19, 2022) -> 1400+ days",
           cards[0].age_days >= 1400, f"{cards[0].age_days} days")
check_true("card 1 (May 23, 2023) -> 1100+ days",
           cards[1].age_days >= 1100, f"{cards[1].age_days} days")
check("card 2 ('1 day ago') -> 1", cards[2].age_days, 1)
check("card 3 (no date, digit-heavy title) -> unknown, not misdated",
      cards[3].age_days, UNKNOWN_AGE)

check("stale card 0 vetoed end-to-end", score_search(cards[0]), 0.0)
check("stale card 1 vetoed end-to-end", score_search(cards[1]), 0.0)
check_true("fresh card 2 passes end-to-end", score_search(cards[2]) > 0.0,
           f"score {score_search(cards[2])}")

# ---------------------------------------------------------------------------
print("\n[6] Gari.pk detail page — the 'Date Posted' spec row")
# ---------------------------------------------------------------------------
DETAIL_HTML = """
<div id="specs-desc">
  <div class="inner-desc"><div class="desc1"><strong>Body Type</strong></div>
    <div class="desc2">Micro Van</div></div>
  <div class="inner-desc"><div class="desc1"><strong>Date Posted</strong></div>
    <div class="desc2">{date}</div></div>
  <div class="inner-desc"><div class="desc1"><strong>Engine Cap.</strong></div>
    <div class="desc2">660 cc</div></div>
</div>
"""
check_true("detail 'Jul 19, 2022' -> 1400+ days",
           parse_detail_age_days(DETAIL_HTML.format(date="Jul 19, 2022")) >= 1400,
           f"{parse_detail_age_days(DETAIL_HTML.format(date='Jul 19, 2022'))} days")

recent = days_ago(3)
check("detail '%s' -> 3 days" % recent,
      parse_detail_age_days(DETAIL_HTML.format(date=recent)), 3)
check("detail page with no Date Posted row -> unknown",
      parse_detail_age_days("<div class='inner-desc'>nothing here</div>"),
      UNKNOWN_AGE)

# ---------------------------------------------------------------------------
print(f"\n{'=' * 60}")
print(f"  {_passed} passed, {_failed} failed")
print(f"{'=' * 60}\n")
sys.exit(1 if _failed else 0)
