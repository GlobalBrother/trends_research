"""Pydantic v2 response models for the FastAPI routers.

Public re-exports group models by router file (mirrors ``src/api/routes/``).
"""

from .common import MessageResponse, OkResponse, OpenModel, RootResponse
from .trends import TrendRow, TrendsResponse
from .content import (
    InstagramPostRow,
    InstagramPostsResponse,
    RedditPostRow,
    RedditPostsResponse,
    ThreadsPostRow,
    ThreadsPostsResponse,
    TiktokVideoRow,
    TiktokVideosResponse,
    YoutubeVideoRow,
    YoutubeVideosResponse,
)
from .ads import (
    AdsInsightResponse,
    AdsInsightRow,
    BrandSearchResponse,
)
from .niches import NicheKeywordsResponse, NicheMutationResponse
from .auth import (
    OtpRequestResponse,
    OtpVerifyResponse,
    TokenValidationResponse,
    UserMutationResponse,
    UserRow,
)
from .admin import (
    AzureDiagnoseResponse,
    AzureStatusResponse,
    MigrationResponse,
    ResetDefaultsResponse,
    TableFiltersResponse,
    TokenUsageResponse,
    TokenUsageRow,
    TokenUsageSummary,
)
from .scrape import ScrapeErrorRow, ScrapeErrorsResponse

__all__ = [
    # common
    "MessageResponse", "OkResponse", "OpenModel", "RootResponse",
    # trends
    "TrendRow", "TrendsResponse",
    # content
    "YoutubeVideoRow", "YoutubeVideosResponse",
    "TiktokVideoRow", "TiktokVideosResponse",
    "InstagramPostRow", "InstagramPostsResponse",
    "RedditPostRow", "RedditPostsResponse",
    "ThreadsPostRow", "ThreadsPostsResponse",
    # ads
    "AdsInsightRow", "AdsInsightResponse", "BrandSearchResponse",
    # niches
    "NicheKeywordsResponse", "NicheMutationResponse",
    # auth
    "OtpRequestResponse", "OtpVerifyResponse", "TokenValidationResponse",
    "UserRow", "UserMutationResponse",
    # admin
    "TokenUsageRow", "TokenUsageSummary", "TokenUsageResponse",
    "AzureStatusResponse", "AzureDiagnoseResponse", "MigrationResponse",
    "TableFiltersResponse", "ResetDefaultsResponse",
    # scrape
    "ScrapeErrorRow", "ScrapeErrorsResponse",
]

