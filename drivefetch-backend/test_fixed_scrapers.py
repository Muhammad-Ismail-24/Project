"""
test_fixed_scrapers.py

Live smoke test for the three scrapers that had been returning 0 listings:
Drive.pk, AutoDeals and FameWheels.

All three sites are now client-rendered SPAs whose HTML contains no listing
markup, so each scraper was rebuilt against the site's own JSON API. This test
hits those APIs for real — it needs network access.

Checks per platform:
  - a populated list of CarListing objects comes back
  - price / year / mileage clean to sensible integers
  - age_days is an int, is never the old 999 sentinel, and is either
    UNKNOWN_AGE (-1) or a plausible non-negative age
  - listing_url and image_url are absolute URLs (image may be blank)
  - prints the first 2 results per platform

Run:  python test_fixed_scrapers.py
"""
import asyncio
import sys

from curl_cffi.requests import AsyncSession

from models.car_schema import CarListing
from scrapers.auto_deals import scrape_auto_deals
from scrapers.date_utils import UNKNOWN_AGE, is_unknown_age
from scrapers.drive_pk import scrape_drive_pk
from scrapers.famewheels import scrape_famewheels
from scrapers.normalizer import _clean_int, _clean_price

# The exact URL shapes runner.py builds for a "Toyota Corolla" search.
DRIVE_URL = ("https://www.drivepk.com/cars/list?page=1&brands=Toyota"
             "&minPrice=1000000&maxPrice=9000000&q=Corolla")
AUTODEALS_URL = ("https://autodeals.pk/used-cars/search/-/minP_1000000/maxP_9000000"
                 "/searchStr_toyota-corolla?page=1")
FAMEWHEELS_URL = "https://www.famewheels.com/used-cars?make=toyota&model=corolla&city="

_failed = 0
_passed = 0


def check(label, condition, detail=""):
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"    PASS  {label}{(' - ' + str(detail)) if detail else ''}")
    else:
        _failed += 1
        print(f"    FAIL  {label}{(' - ' + str(detail)) if detail else ''}")


def audit(platform: str, cars: list) -> None:
    print(f"\n  [{platform}] returned {len(cars)} listings")

    check("returns a non-empty list", len(cars) > 0, f"{len(cars)} listings")
    if not cars:
        return

    check("all items are CarListing",
          all(isinstance(c, CarListing) for c in cars))
    check("platform tag set on every listing",
          all(c.platform for c in cars),
          sorted({c.platform for c in cars}))

    # --- age_days ---
    ages = [c.age_days for c in cars]
    check("age_days is always int", all(isinstance(a, int) for a in ages))
    check("age_days never uses the retired 999 sentinel", 999 not in ages)
    check("age_days is UNKNOWN_AGE or >= 0",
          all(a == UNKNOWN_AGE or a >= 0 for a in ages))
    known = [a for a in ages if not is_unknown_age(a)]
    check("at least one listing has a known age",
          len(known) > 0, f"{len(known)}/{len(cars)} dated")
    if known:
        check("known ages are plausible (< 20 years)",
              max(known) < 20 * 365, f"min={min(known)}d max={max(known)}d")

    # --- typed numeric fields ---
    prices = [_clean_price(c.price) for c in cars]
    years = [_clean_int(c.year) for c in cars]
    miles = [_clean_int(c.mileage) for c in cars]
    check("price cleans to int > 0 for most listings",
          sum(1 for p in prices if p > 0) >= max(1, len(cars) // 2),
          f"{sum(1 for p in prices if p > 0)}/{len(cars)} priced")
    check("year cleans to a sane range",
          all(y == 0 or 1980 <= y <= 2030 for y in years),
          f"{min(years)}..{max(years)}")
    check("mileage cleans to a non-negative int",
          all(isinstance(m, int) and m >= 0 for m in miles))

    # --- urls ---
    check("listing_url is absolute on every listing",
          all(c.listing_url.startswith("http") for c in cars))
    check("image_url is str (never None) and absolute when present",
          all(isinstance(c.image_url, str) and
              (c.image_url == "" or c.image_url.startswith("http")) for c in cars),
          f"{sum(1 for c in cars if c.image_url)}/{len(cars)} with images")

    print(f"\n    --- first 2 {platform} results ---")
    for c in cars[:2]:
        age = "UNKNOWN" if is_unknown_age(c.age_days) else f"{c.age_days}d"
        print(f"      title   : {c.title[:66]}")
        print(f"      price   : {_clean_price(c.price):,} PKR   year: {_clean_int(c.year)}   "
              f"mileage: {_clean_int(c.mileage):,} km")
        print(f"      city    : {c.city}      age_days: {c.age_days} ({age})")
        print(f"      url     : {c.listing_url[:96]}")
        print(f"      image   : {(c.image_url or '(none)')[:96]}")
        print()


async def main():
    print("=" * 78)
    print("  Live scrape: Toyota Corolla")
    print("=" * 78)

    async with AsyncSession(impersonate="chrome120") as session:
        drive, deals, fame = await asyncio.gather(
            scrape_drive_pk(DRIVE_URL, session, {}),
            scrape_auto_deals(AUTODEALS_URL, session, {}),
            scrape_famewheels(FAMEWHEELS_URL, session),
            return_exceptions=True,
        )

    for name, result in (("Drive.pk", drive), ("AutoDeals", deals),
                         ("FameWheels", fame)):
        if isinstance(result, Exception):
            global _failed
            _failed += 1
            print(f"\n  [{name}] FAIL  raised {type(result).__name__}: {result}")
            continue
        audit(name, result)

    print("=" * 78)
    print(f"  {_passed} passed, {_failed} failed")
    print("=" * 78)
    sys.exit(1 if _failed else 0)


asyncio.run(main())
