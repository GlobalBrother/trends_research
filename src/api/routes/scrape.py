"""Scraping endpoints (`/scrape`, `/scrape_ads`, `/scrape_brand_ads`,
`/scrape_errors`, `/import_tokens`)."""

import json
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from src.api.dependencies import (
    HAS_GETHOOKEDAI,
    _get_niche_keywords_from_db,
    _run_and_log,
    _sanitize,
    collector,
    gethookd_scrape_ads,
    gethookd_scrape_brand_ads,
    logger,
    session_scope,
)
from src.api.schemas import MessageResponse, OkResponse, ScrapeErrorsResponse
from src.db.models import ScrapeError as ScrapeErrorModel

router = APIRouter(tags=["scrape"])


class ScrapeRequest(BaseModel):
    niche: str
    geo: str = "US"
    timeframe: str = "today 12-m"
    category: int = 0
    scraper_type: str = "all"


@router.post("/scrape", response_model=MessageResponse)
def scrape_niche(request: ScrapeRequest, background_tasks: BackgroundTasks):
    niche_keywords = _get_niche_keywords_from_db(request.niche)
    scraper = request.scraper_type

    if scraper == "all":
        background_tasks.add_task(
            _run_and_log, collector.run_niche_comprehensive_scrape,
            "all", niche_keywords, request.geo,
            niche_name=request.niche,
            keywords=niche_keywords,
            geo=request.geo,
            timeframe=request.timeframe,
            category=request.category
        )
    elif scraper == "google_trends":
        background_tasks.add_task(
            _run_and_log, collector.run_google_trends_scraper,
            "google_trends", niche_keywords, request.geo,
            keywords=niche_keywords, geo=request.geo,
            timeframe=request.timeframe, category=request.category
        )
    elif scraper == "daily":
        background_tasks.add_task(
            _run_and_log, collector.run_trending_now_scraper,
            "daily", request.niche, request.geo,
            geo=request.geo
        )
    elif scraper == "youtube":
        background_tasks.add_task(
            _run_and_log, collector.run_youtube_trends_scraper,
            "youtube", niche_keywords, request.geo,
            keywords=niche_keywords, geo=request.geo
        )
    elif scraper in ("Threads", "Instagram", "TikTok"):
        background_tasks.add_task(
            _run_and_log, collector.run_social_trends_scraper,
            scraper, niche_keywords, request.geo,
            platform=scraper, keywords=niche_keywords, geo=request.geo
        )
    elif scraper == "hackernews":
        background_tasks.add_task(
            _run_and_log, collector.run_hackernews_scraper,
            "hackernews", niche_keywords, request.geo,
            keywords=niche_keywords, geo=request.geo
        )
    elif scraper == "reddit":
        background_tasks.add_task(
            _run_and_log, collector.run_reddit_scraper,
            "reddit", niche_keywords, request.geo,
            keywords=niche_keywords, geo=request.geo
        )
    elif scraper == "news":
        background_tasks.add_task(
            _run_and_log, collector.run_news_scraper,
            "news", request.niche, request.geo,
            query=request.niche, geo=request.geo
        )
    else:
        background_tasks.add_task(
            _run_and_log, collector.run_niche_comprehensive_scrape,
            "all", niche_keywords, request.geo,
            niche_name=request.niche,
            keywords=niche_keywords,
            geo=request.geo,
            timeframe=request.timeframe,
            category=request.category
        )

    return {"message": f"Scraping ({scraper}) for {request.niche} started in background. Results will be available soon."}


@router.post("/import_tokens", response_model=MessageResponse)
async def import_tokens(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    geo: str = Query("US"),
):
    """
    Import a Google Trends JSON file downloaded manually when the API returns 429.
    Parses widget tokens and fetches data using those tokens directly.
    """
    try:
        content = await file.read()
        text = content.decode("utf-8")

        # Strip Google's XSSI prefix which can appear in various forms:
        # )]}'\n{...}  or  )\n]\n}'\n{...}  or  )]}',\n{...}
        # Find the first '{' which starts the actual JSON object
        brace_idx = text.find("{")
        if brace_idx > 0:
            text = text[brace_idx:]

        data = json.loads(text)
        widgets = data.get("widgets", [])
        if not widgets:
            raise HTTPException(status_code=400, detail="No widgets found in the uploaded JSON file.")

        # Extract keyword from the JSON
        keywords_info = data.get("keywords", [])
        keyword = keywords_info[0].get("keyword", "Unknown") if keywords_info else "Unknown"

        # Extract geo from widget requests if not provided
        for w in widgets:
            req = w.get("request", {})
            widget_geo = req.get("geo", {}).get("country") or req.get("restriction", {}).get("geo", {}).get("country")
            if widget_geo:
                geo = widget_geo
                break

        widgets_json = json.dumps(widgets)

        background_tasks.add_task(
            _run_and_log, collector.run_token_import,
            "import_tokens", keyword, geo,
            widgets_json=widgets_json,
            geo=geo,
            keyword=keyword,
        )

        return {
            "message": f"Token import started for keyword '{keyword}' (geo={geo}). "
                       f"Found {len(widgets)} widget(s). Data will be available soon."
        }
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing tokens: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrape_ads", response_model=MessageResponse)
def scrape_ads_endpoint(
    background_tasks: BackgroundTasks,
    keywords: str = Query(..., description="Comma-separated keywords"),
    max_pages: int = Query(3),
):
    if not HAS_GETHOOKEDAI:
        raise HTTPException(status_code=501, detail="GetHookdAI scraper not available")
    kws = [k.strip() for k in keywords.split(",") if k.strip()]
    if not kws:
        raise HTTPException(status_code=400, detail="No keywords provided")
    background_tasks.add_task(
        _run_and_log, gethookd_scrape_ads,
        "ads_insight", kws, None,
        keywords=kws, max_pages=max_pages,
    )
    return {"message": f"Ads scrape started for: {', '.join(kws)}"}


@router.post("/scrape_brand_ads", response_model=MessageResponse)
def scrape_brand_ads_endpoint(
    background_tasks: BackgroundTasks,
    brand_id: int = Query(...),
):
    if not HAS_GETHOOKEDAI:
        raise HTTPException(status_code=501, detail="GetHookdAI scraper not available")
    background_tasks.add_task(
        _run_and_log, gethookd_scrape_brand_ads,
        "ads_brand_spy", str(brand_id), None,
        brand_id=brand_id,
    )
    return {"message": f"Brand spy started for brand {brand_id}"}


@router.get("/scrape_errors", response_model=ScrapeErrorsResponse)
def get_scrape_errors(platform: Optional[str] = Query(None)):
    df = collector.get_scrape_errors(platform=platform)
    if df.empty:
        return {"data": []}
    return {"data": _sanitize(df)}


@router.delete("/scrape_errors", response_model=OkResponse)
def clear_scrape_errors():
    try:
        with session_scope() as session:
            session.query(ScrapeErrorModel).delete()
        return {"ok": True}
    except Exception as e:
        logger.error(f"Failed to clear scrape_errors: {e}")
        raise HTTPException(status_code=500, detail=str(e))

