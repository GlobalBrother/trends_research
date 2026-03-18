"""Ads Insight scraper using the GetHookd AI API.

Searches the GetHookd ad library (21M+ ads) for given keywords and stores
comprehensive ad data into a dedicated ``ads_insight`` table as well as the
shared ``trends`` table for cross-platform dashboards.

Endpoints covered (from md.json OpenAPI spec):
  - GET  /api/v1/authcheck
  - GET  /api/v1/explore           (search/filter ads)
  - GET  /api/v1/brandspy          (list spied brands)
  - GET  /api/v1/brandspy/{id}     (brand details + paginated ads)
  - POST /api/v1/brandspy          (add brand to spy)
  - DELETE /api/v1/brandspy/{id}   (remove spied brand)
  - GET  /api/v1/swipefile         (list saved ads)
  - POST /api/v1/swipefile         (save ad)
  - DELETE /api/v1/swipefile/{id}  (remove saved ad)
  - GET  /api/v1/boards            (list boards)
  - POST /api/v1/boards            (create board)
  - GET  /api/v1/boards/{id}       (board details)
  - PUT  /api/v1/boards/{id}       (update board)
  - DELETE /api/v1/boards/{id}     (delete board)
  - POST /api/v1/boards/{id}/ads   (add ad to board)
  - DELETE /api/v1/boards/{id}/ads/{ad_id} (remove ad from board)
  - GET  /api/v1/clone-ads         (list clone history)
  - POST /api/v1/clone-ads         (generate cloned variations)
  - GET  /api/v1/clone-ads/{id}    (view clone result)
"""

import json
import logging
import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "ensembledata"))
from db_helper import save_trend, save_error

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
from src.db.connection import get_session
from src.db.models import AdsInsight

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

PLATFORM = "GetHookdAI"
BASE_URL = "https://app.gethookd.ai/api/v1"

# ---------------------------------------------------------------------------
# Explore filter parameter names (from md.json)
# ---------------------------------------------------------------------------
# query, page, per_page, sort_column, sort_direction, start-date, end-date,
# status, ad-format, run-time, language, platform, niche,
# performance_scores, used_count, video_lengths, eu_transparency,
# eu_total_reach, gender_audience, age_audience, location,
# ad_spend_range, excluded_brands, creative_categories, cta_types,
# active_ads_count, ads_per_brand_limit

# ---------------------------------------------------------------------------
# Ads Insight table — matches PublicAd schema from md.json
# ---------------------------------------------------------------------------

_CREATE_ADS_INSIGHT = """
CREATE TABLE IF NOT EXISTS ads_insight (
    -- identifiers
    hookd_id                INTEGER PRIMARY KEY,
    external_id             TEXT,
    search_keyword          TEXT,

    -- content
    platform                TEXT,
    display_format          TEXT,
    title                   TEXT,
    body                    TEXT,
    landing_page            TEXT,
    link_description        TEXT,
    cta_type                TEXT,
    cta_text                TEXT,

    -- scheduling
    start_date              TEXT,
    end_date                TEXT,
    days_active             INTEGER DEFAULT 0,
    active_in_library       INTEGER DEFAULT 0,

    -- performance
    performance_score       INTEGER,
    performance_score_title TEXT,
    used_count              INTEGER DEFAULT 0,
    is_aaa_eligible         INTEGER,

    -- audience
    age_audience_min        INTEGER,
    age_audience_max        INTEGER,
    gender_audience         TEXT,
    eu_total_reach          INTEGER,

    -- spend
    ad_spend_range_score        INTEGER,
    ad_spend_range_score_title  TEXT,

    -- brand (PublicBrand schema)
    brand_external_id       TEXT,
    brand_name              TEXT,
    brand_logo_url          TEXT,
    brand_active_ads        INTEGER DEFAULT 0,

    -- media (JSON array of PublicAdMedia)
    media                   TEXT,

    -- ad cards (JSON array of PublicAdCard)
    ad_cards                TEXT,

    -- share
    share_url               TEXT,

    -- metadata
    extracted_at            TEXT,
    updated_at              TEXT
);
"""


def _ensure_table():
    """Tables are pre-created in Azure SQL via migration schema."""
    pass


def _get_headers():
    token = os.getenv("GETHOOKEDAI_TOKEN", "")
    if not token:
        raise RuntimeError("GETHOOKEDAI_TOKEN not set in environment")
    return {"Authorization": f"Bearer {token}"}


def _handle_rate_limit(resp):
    """If 429, sleep for Retry-After seconds and return True (should retry)."""
    if resp.status_code == 429:
        retry_after = int(resp.headers.get("Retry-After", 5))
        logger.warning("Rate limited, waiting %ds", retry_after)
        time.sleep(retry_after)
        return True
    return False


def _handle_credits(resp, keyword=""):
    """If 402, log and save error. Returns True if credits exhausted."""
    if resp.status_code == 402:
        body = resp.json()
        data = body.get("data", {})
        logger.error(
            "GetHookdAI: not enough credits (needed=%.2f, remaining=%s)",
            data.get("credits_needed", 0), data.get("remaining_credits", "?"),
        )
        save_error(PLATFORM, keyword, resp.url, 402, "Not enough credits")
        return True
    return False


def _save_ad(ad: dict, keyword: str):
    """Persist a single ad record into the ads_insight table using ORM.

    Fields mapped from PublicAd schema (md.json).
    """
    now = datetime.now()
    brand = ad.get("brand") or {}
    media = ad.get("media") or []
    ad_cards = ad.get("ad_cards") or []

    fields = {
        "external_id": ad.get("external_id"), "search_keyword": keyword,
        "platform": ad.get("platform"), "display_format": ad.get("display_format"),
        "title": ad.get("title"), "body": ad.get("body"),
        "landing_page": ad.get("landing_page"), "link_description": ad.get("link_description"),
        "cta_type": ad.get("cta_type"), "cta_text": ad.get("cta_text"),
        "start_date": ad.get("start_date"), "end_date": ad.get("end_date"),
        "days_active": ad.get("days_active", 0), "active_in_library": ad.get("active_in_library", 0),
        "performance_score": ad.get("performance_score"),
        "performance_score_title": ad.get("performance_score_title"),
        "used_count": ad.get("used_count", 0), "is_aaa_eligible": ad.get("is_aaa_eligible"),
        "age_audience_min": ad.get("age_audience_min"), "age_audience_max": ad.get("age_audience_max"),
        "gender_audience": ad.get("gender_audience"), "eu_total_reach": ad.get("eu_total_reach"),
        "ad_spend_range_score": ad.get("ad_spend_range_score"),
        "ad_spend_range_score_title": ad.get("ad_spend_range_score_title"),
        "brand_external_id": brand.get("external_id"), "brand_name": brand.get("name"),
        "brand_logo_url": brand.get("logo_url"), "brand_active_ads": brand.get("active_ads", 0),
        "media": json.dumps(media), "ad_cards": json.dumps(ad_cards),
        "share_url": ad.get("share_url"),
        "updated_at": now,
    }

    session = get_session()
    try:
        existing = session.query(AdsInsight).filter(AdsInsight.hookd_id == ad.get("id")).first()
        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
        else:
            fields["hookd_id"] = ad.get("id")
            fields["extracted_at"] = now
            session.add(AdsInsight(**fields))
        session.commit()
    except Exception:
        session.rollback()
        logger.error("Failed to save ad hookd_id=%s, keyword=%s", ad.get("id"), keyword, exc_info=True)
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def auth_check():
    """GET /api/v1/authcheck — validate token and return workspace info + scopes."""
    logger.info("GetHookdAI: checking authentication...")
    headers = _get_headers()
    resp = requests.get(f"{BASE_URL}/authcheck", headers=headers, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    logger.info("GetHookdAI: auth check OK — workspace=%s, scopes=%s",
                result.get('data', {}).get('workspace', {}).get('name'),
                result.get('data', {}).get('scopes'))
    return result


# ---------------------------------------------------------------------------
# Explore — search & filter ads
# ---------------------------------------------------------------------------

def scrape_ads(keywords, max_pages=3, **filters):
    """Search the GetHookd ad library for each keyword and persist results.

    Parameters
    ----------
    keywords : list[str]
        Keywords to search for in the ad library.
    max_pages : int
        Maximum number of pages to fetch per keyword.
    **filters : dict
        Optional explore filters from md.json spec:
        per_page (1-100, default 20), sort_column, sort_direction,
        start_date, end_date, status, ad_format, run_time, language,
        platform, niche, performance_scores, used_count, video_lengths,
        eu_transparency, eu_total_reach, gender_audience, age_audience,
        location, ad_spend_range, excluded_brands, creative_categories,
        cta_types, active_ads_count, ads_per_brand_limit.
    """
    _ensure_table()
    headers = _get_headers()

    # Map Python-friendly filter names to API parameter names (hyphenated)
    _FILTER_MAP = {
        "per_page": "per_page",
        "sort_column": "sort_column",
        "sort_direction": "sort_direction",
        "start_date": "start-date",
        "end_date": "end-date",
        "status": "status",
        "ad_format": "ad-format",
        "run_time": "run-time",
        "language": "language",
        "platform": "platform",
        "niche": "niche",
        "performance_scores": "performance_scores",
        "used_count": "used_count",
        "video_lengths": "video_lengths",
        "eu_transparency": "eu_transparency",
        "eu_total_reach": "eu_total_reach",
        "gender_audience": "gender_audience",
        "age_audience": "age_audience",
        "location": "location",
        "ad_spend_range": "ad_spend_range",
        "excluded_brands": "excluded_brands",
        "creative_categories": "creative_categories",
        "cta_types": "cta_types",
        "active_ads_count": "active_ads_count",
        "ads_per_brand_limit": "ads_per_brand_limit",
    }

    extra_params = {}
    for py_key, api_key in _FILTER_MAP.items():
        if py_key in filters and filters[py_key] is not None:
            extra_params[api_key] = filters[py_key]

    for keyword in keywords:
        logger.info("GetHookdAI: searching ads for keyword=%s", keyword)
        page = 1
        total_saved = 0

        while page <= max_pages:
            params = {"query": keyword, "page": page, **extra_params}
            try:
                resp = requests.get(
                    f"{BASE_URL}/explore",
                    headers=headers,
                    params=params,
                    timeout=30,
                )

                if _handle_rate_limit(resp):
                    continue
                if _handle_credits(resp, keyword):
                    return

                resp.raise_for_status()
                data = resp.json()

                ads = data.get("data", [])
                if not ads:
                    logger.info("GetHookdAI: no more ads for keyword=%s at page=%d", keyword, page)
                    break

                for ad in ads:
                    _save_ad(ad, keyword)

                    topic = ad.get("title") or (ad.get("body") or "")[:120]
                    brand = ad.get("brand") or {}
                    save_trend(
                        platform=PLATFORM,
                        topic=topic,
                        growth=ad.get("performance_score", 0),
                        keyword=keyword,
                        geo="Global",
                        url=ad.get("share_url") or ad.get("landing_page") or "",
                        extra_data={
                            "hookd_id": ad.get("id"),
                            "display_format": ad.get("display_format"),
                            "brand_name": brand.get("name"),
                            "days_active": ad.get("days_active"),
                            "performance_score_title": ad.get("performance_score_title"),
                            "cta_type": ad.get("cta_type"),
                        },
                    )
                    total_saved += 1

                remaining = data.get("remaining_credits")
                logger.info(
                    "GetHookdAI: page %d done for keyword=%s (%d ads). Credits remaining: %s",
                    page, keyword, len(ads), remaining,
                )

                # Explore pagination: meta object at root level
                meta = data.get("meta", {})
                last_page = meta.get("last_page", page)
                if page >= last_page:
                    break

                page += 1
                time.sleep(0.25)

            except requests.RequestException as exc:
                logger.error("GetHookdAI: request failed for keyword=%s page=%d: %s", keyword, page, exc)
                save_error(PLATFORM, keyword, f"{BASE_URL}/explore", getattr(exc.response, "status_code", 0) if exc.response else 0, str(exc))
                break

        logger.info("GetHookdAI: saved %d ads for keyword=%s", total_saved, keyword)


# ---------------------------------------------------------------------------
# Brand Spy
# ---------------------------------------------------------------------------

def list_spied_brands(page=1, per_page=20, sort_column="created_at", sort_direction="desc"):
    """GET /api/v1/brandspy — list spied brands with pagination.

    Returns dict with keys: data (list of PublicSpiedBrand), meta, used_credits, remaining_credits.
    PublicSpiedBrand fields: id, brand_id, brand_external_id, brand_name, brand_logo_url,
    status, active_ads, inactive_ads, videos, images, carousels, created_at, last_spied_at.
    """
    logger.info("GetHookdAI: listing spied brands (page=%d, per_page=%d)", page, per_page)
    headers = _get_headers()
    params = {"page": page, "per_page": per_page, "sort_column": sort_column, "sort_direction": sort_direction}
    resp = requests.get(f"{BASE_URL}/brandspy", headers=headers, params=params, timeout=30)
    if _handle_rate_limit(resp):
        resp = requests.get(f"{BASE_URL}/brandspy", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    logger.info("GetHookdAI: found %d spied brands", len(result.get('data', [])))
    return result


def scrape_brand_ads(brand_id, max_pages=5, status=None, platform=None, ad_format=None):
    """GET /api/v1/brandspy/{brand_id} — fetch brand details + paginated ads.

    Response structure (from md.json):
      data.id, data.brand_id, data.brand_external_id, data.brand_name, data.brand_logo_url,
      data.status, data.active_ads, data.inactive_ads, data.videos, data.images, data.carousels,
      data.created_at, data.last_spied_at,
      data.ads.data[] (array of PublicAd), data.ads.current_page, data.ads.per_page,
      data.ads.total, data.ads.last_page

    Parameters
    ----------
    brand_id : int
        The brand ID to spy on.
    max_pages : int
        Maximum pages of ads to fetch.
    status : str, optional
        Filter by ad status: "active" or "inactive".
    platform : str, optional
        Filter by platform (facebook, instagram, tiktok, etc.).
    ad_format : str, optional
        Filter by format (image, video, carousel, etc.).
    """
    _ensure_table()
    headers = _get_headers()
    keyword = f"brand:{brand_id}"

    logger.info("GetHookdAI: fetching brand ads for brand_id=%s", brand_id)
    page = 1
    total_saved = 0

    while page <= max_pages:
        params = {"page": page, "per_page": 20}
        if status:
            params["status"] = status
        if platform:
            params["platform"] = platform
        if ad_format:
            params["ad-format"] = ad_format

        try:
            resp = requests.get(
                f"{BASE_URL}/brandspy/{brand_id}",
                headers=headers,
                params=params,
                timeout=30,
            )

            if _handle_rate_limit(resp):
                continue
            if _handle_credits(resp, keyword):
                return

            resp.raise_for_status()
            body = resp.json()

            # brandspy/{id} nests ads inside data.ads.data (per md.json spec)
            brand_data = body.get("data", {})
            ads_wrapper = brand_data.get("ads", {})
            ads = ads_wrapper.get("data", [])

            if not ads:
                logger.info("GetHookdAI: no more brand ads at page=%d", page)
                break

            for ad in ads:
                _save_ad(ad, keyword)
                total_saved += 1

            last_page = ads_wrapper.get("last_page", page)
            if page >= last_page:
                break

            page += 1
            time.sleep(0.25)

        except requests.RequestException as exc:
            logger.error("GetHookdAI: brand spy failed for brand_id=%s: %s", brand_id, exc)
            save_error(PLATFORM, keyword, f"{BASE_URL}/brandspy/{brand_id}",
                       getattr(exc.response, "status_code", 0) if exc.response else 0, str(exc))
            break

    logger.info("GetHookdAI: saved %d brand ads for brand_id=%s", total_saved, brand_id)


def search_brands(query, per_page=10):
    """Search brands by name using the explore endpoint.

    Returns a list of unique brands matching the query, each with:
    brand_id (internal), external_id, name, logo_url, active_ads.
    """
    logger.info("GetHookdAI: searching brands for query=%s", query)
    headers = _get_headers()
    params = {"query": query, "per_page": per_page}
    resp = requests.get(f"{BASE_URL}/explore", headers=headers, params=params, timeout=30)
    if _handle_rate_limit(resp):
        resp = requests.get(f"{BASE_URL}/explore", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    ads = resp.json().get("data", [])
    seen = set()
    brands = []
    for ad in ads:
        b = ad.get("brand") or {}
        name = b.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        brands.append({
            "external_id": b.get("external_id"),
            "name": name,
            "logo_url": b.get("logo_url"),
            "active_ads": b.get("active_ads", 0),
        })
    return brands


def add_spied_brand(brand_id):
    """POST /api/v1/brandspy — add a brand to spy on.

    Body: {"brand_id": <int>}
    Returns the newly spied brand. 409 if already spied.
    """
    logger.info("GetHookdAI: adding brand_id=%s to spy list", brand_id)
    headers = _get_headers()
    headers["Content-Type"] = "application/json"
    resp = requests.post(
        f"{BASE_URL}/brandspy", headers=headers,
        json={"brand_id": brand_id}, timeout=15,
    )
    if _handle_rate_limit(resp):
        resp = requests.post(f"{BASE_URL}/brandspy", headers=headers, json={"brand_id": brand_id}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def remove_spied_brand(brand_id):
    """DELETE /api/v1/brandspy/{brand_id} — remove a spied brand."""
    logger.info("GetHookdAI: removing brand_id=%s from spy list", brand_id)
    headers = _get_headers()
    resp = requests.delete(f"{BASE_URL}/brandspy/{brand_id}", headers=headers, timeout=15)
    if _handle_rate_limit(resp):
        resp = requests.delete(f"{BASE_URL}/brandspy/{brand_id}", headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Swipe File
# ---------------------------------------------------------------------------

def list_swipefile(page=1, per_page=20, sort_column="created_at", sort_direction="desc"):
    """GET /api/v1/swipefile — list saved ads with pagination.

    Returns dict with data (PublicAd[]), meta (PaginationMeta), used_credits, remaining_credits.
    """
    logger.info("GetHookdAI: listing swipefile (page=%d)", page)
    headers = _get_headers()
    params = {"page": page, "per_page": per_page, "sort_column": sort_column, "sort_direction": sort_direction}
    resp = requests.get(f"{BASE_URL}/swipefile", headers=headers, params=params, timeout=30)
    if _handle_rate_limit(resp):
        resp = requests.get(f"{BASE_URL}/swipefile", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def save_to_swipefile(ad_id):
    """POST /api/v1/swipefile — save an ad to swipe file.

    Body: {"ad_id": <int>}
    Returns 409 if already saved.
    """
    logger.info("GetHookdAI: saving ad_id=%s to swipefile", ad_id)
    headers = _get_headers()
    headers["Content-Type"] = "application/json"
    resp = requests.post(
        f"{BASE_URL}/swipefile", headers=headers,
        json={"ad_id": ad_id}, timeout=15,
    )
    if _handle_rate_limit(resp):
        resp = requests.post(f"{BASE_URL}/swipefile", headers=headers, json={"ad_id": ad_id}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def remove_from_swipefile(ad_id):
    """DELETE /api/v1/swipefile/{ad_id} — remove an ad from swipe file."""
    logger.info("GetHookdAI: removing ad_id=%s from swipefile", ad_id)
    headers = _get_headers()
    resp = requests.delete(f"{BASE_URL}/swipefile/{ad_id}", headers=headers, timeout=15)
    if _handle_rate_limit(resp):
        resp = requests.delete(f"{BASE_URL}/swipefile/{ad_id}", headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Boards
# ---------------------------------------------------------------------------

def list_boards(page=1, per_page=20, sort_column="created_at", sort_direction="desc"):
    """GET /api/v1/boards — list boards with pagination.

    Returns dict with data (PublicBoard[]), meta, used_credits, remaining_credits.
    PublicBoard fields: id, name, description, ads_count, created_at, updated_at.
    """
    logger.info("GetHookdAI: listing boards (page=%d)", page)
    headers = _get_headers()
    params = {"page": page, "per_page": per_page, "sort_column": sort_column, "sort_direction": sort_direction}
    resp = requests.get(f"{BASE_URL}/boards", headers=headers, params=params, timeout=30)
    if _handle_rate_limit(resp):
        resp = requests.get(f"{BASE_URL}/boards", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def create_board(name, description=""):
    """POST /api/v1/boards — create a new board.

    Body: {"name": <str>, "description": <str>}
    """
    logger.info("GetHookdAI: creating board name=%s", name)
    headers = _get_headers()
    headers["Content-Type"] = "application/json"
    resp = requests.post(
        f"{BASE_URL}/boards", headers=headers,
        json={"name": name, "description": description}, timeout=15,
    )
    if _handle_rate_limit(resp):
        resp = requests.post(f"{BASE_URL}/boards", headers=headers, json={"name": name, "description": description}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_board(board_id, page=1, per_page=20):
    """GET /api/v1/boards/{board_id} — board details with paginated ads."""
    logger.info("GetHookdAI: getting board_id=%s", board_id)
    headers = _get_headers()
    params = {"page": page, "per_page": per_page}
    resp = requests.get(f"{BASE_URL}/boards/{board_id}", headers=headers, params=params, timeout=30)
    if _handle_rate_limit(resp):
        resp = requests.get(f"{BASE_URL}/boards/{board_id}", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def update_board(board_id, name=None, description=None):
    """PUT /api/v1/boards/{board_id} — update board name/description."""
    logger.info("GetHookdAI: updating board_id=%s", board_id)
    headers = _get_headers()
    headers["Content-Type"] = "application/json"
    body = {}
    if name is not None:
        body["name"] = name
    if description is not None:
        body["description"] = description
    resp = requests.put(f"{BASE_URL}/boards/{board_id}", headers=headers, json=body, timeout=15)
    if _handle_rate_limit(resp):
        resp = requests.put(f"{BASE_URL}/boards/{board_id}", headers=headers, json=body, timeout=15)
    resp.raise_for_status()
    return resp.json()


def delete_board(board_id):
    """DELETE /api/v1/boards/{board_id} — delete a board."""
    logger.info("GetHookdAI: deleting board_id=%s", board_id)
    headers = _get_headers()
    resp = requests.delete(f"{BASE_URL}/boards/{board_id}", headers=headers, timeout=15)
    if _handle_rate_limit(resp):
        resp = requests.delete(f"{BASE_URL}/boards/{board_id}", headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def add_ad_to_board(board_id, ad_id):
    """POST /api/v1/boards/{board_id}/ads — add an ad to a board.

    Body: {"ad_id": <int>}
    """
    logger.info("GetHookdAI: adding ad_id=%s to board_id=%s", ad_id, board_id)
    headers = _get_headers()
    headers["Content-Type"] = "application/json"
    resp = requests.post(
        f"{BASE_URL}/boards/{board_id}/ads", headers=headers,
        json={"ad_id": ad_id}, timeout=15,
    )
    if _handle_rate_limit(resp):
        resp = requests.post(f"{BASE_URL}/boards/{board_id}/ads", headers=headers, json={"ad_id": ad_id}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def remove_ad_from_board(board_id, ad_id):
    """DELETE /api/v1/boards/{board_id}/ads/{ad_id} — remove an ad from a board."""
    logger.info("GetHookdAI: removing ad_id=%s from board_id=%s", ad_id, board_id)
    headers = _get_headers()
    resp = requests.delete(f"{BASE_URL}/boards/{board_id}/ads/{ad_id}", headers=headers, timeout=15)
    if _handle_rate_limit(resp):
        resp = requests.delete(f"{BASE_URL}/boards/{board_id}/ads/{ad_id}", headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Clone Ads
# ---------------------------------------------------------------------------

def list_clone_ads(page=1, per_page=20):
    """GET /api/v1/clone-ads — list clone history with pagination.

    Returns dict with data (CloneAd[]), meta, used_credits, remaining_credits.
    """
    logger.info("GetHookdAI: listing clone ads (page=%d)", page)
    headers = _get_headers()
    params = {"page": page, "per_page": per_page}
    resp = requests.get(f"{BASE_URL}/clone-ads", headers=headers, params=params, timeout=30)
    if _handle_rate_limit(resp):
        resp = requests.get(f"{BASE_URL}/clone-ads", headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def generate_clone_ad(ad_id, variations=3):
    """POST /api/v1/clone-ads — generate cloned ad variations.

    Body: {"ad_id": <int>, "variations": <int>}
    Cost: 0.01 credits per variation requested.
    """
    logger.info("GetHookdAI: generating %d clone variations for ad_id=%s", variations, ad_id)
    headers = _get_headers()
    headers["Content-Type"] = "application/json"
    resp = requests.post(
        f"{BASE_URL}/clone-ads", headers=headers,
        json={"ad_id": ad_id, "variations": variations}, timeout=30,
    )
    if _handle_rate_limit(resp):
        resp = requests.post(f"{BASE_URL}/clone-ads", headers=headers, json={"ad_id": ad_id, "variations": variations}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_clone_ad(clone_id):
    """GET /api/v1/clone-ads/{clone_id} — view clone result."""
    logger.info("GetHookdAI: getting clone_id=%s", clone_id)
    headers = _get_headers()
    resp = requests.get(f"{BASE_URL}/clone-ads/{clone_id}", headers=headers, timeout=30)
    if _handle_rate_limit(resp):
        resp = requests.get(f"{BASE_URL}/clone-ads/{clone_id}", headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="GetHookd AI Ads Insight scraper")
    parser.add_argument("--keywords", required=True, help="Comma-separated keywords")
    parser.add_argument("--max-pages", type=int, default=3, help="Max pages per keyword")
    parser.add_argument("--brand-id", type=int, default=None, help="Brand ID to spy on")
    parser.add_argument("--per-page", type=int, default=20, help="Results per page (1-100)")
    parser.add_argument("--status", default=None, help="Filter: active or inactive")
    parser.add_argument("--ad-format", default=None, help="Filter: image,video,carousels,...")
    parser.add_argument("--platform", default=None, help="Filter: facebook,instagram,...")
    parser.add_argument("--niche", default=None, help="Filter: niche IDs (CSV)")
    parser.add_argument("--performance-scores", default=None, help="Filter: testing,scaling,growing,optimized,winning")
    parser.add_argument("--cta-types", default=None, help="Filter: SHOP_NOW,LEARN_MORE,...")
    parser.add_argument("--location", default=None, help="Filter: country codes (CSV)")
    parser.add_argument("--language", default=None, help="Filter: language codes (CSV)")
    parser.add_argument("--sort-column", default=None, help="Sort: created_at,start_date,days_active,used_count")
    parser.add_argument("--sort-direction", default=None, help="Sort: asc or desc")
    args = parser.parse_args()

    filters = {}
    for key in ["per_page", "status", "ad_format", "platform", "niche",
                 "performance_scores", "cta_types", "location", "language",
                 "sort_column", "sort_direction"]:
        val = getattr(args, key.replace("-", "_"), None)
        if val is not None:
            filters[key] = val

    kws = [k.strip() for k in args.keywords.split(",")]
    scrape_ads(kws, max_pages=args.max_pages, **filters)

    if args.brand_id:
        scrape_brand_ads(args.brand_id)
