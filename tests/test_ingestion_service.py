from contextlib import contextmanager
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.models import Base, CanonicalTrendSignal, RawDataArchive, ScrapeRun, TrendEvidence
from src.ingestion.service import CanonicalSignalInput, IngestionService
from src.scrapers.ensembledata.db_helper import save_trend
from src.scrapers.google_trends_scraper.google_trends.pipelines import DatabasePipeline


def _make_sqlite_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def fake_session_scope():
        session = TestingSession()
        try:
            yield session
            session.commit()
        finally:
            session.close()

    return TestingSession, fake_session_scope


def test_ingest_signal_is_idempotent(monkeypatch):
    TestingSession, fake_session_scope = _make_sqlite_session()
    monkeypatch.setattr("src.ingestion.service.session_scope", fake_session_scope)

    service = IngestionService()
    signal = CanonicalSignalInput(
        source="YouTube",
        entity_type="video",
        entity_id="vid-1",
        label="AI agents tutorial",
        country="US",
        language="en",
        retrieved_at=datetime.utcnow(),
        granularity="day",
        metrics={"volume": 1000, "growth_rate": 200, "engagement": 400},
        sampled_content_refs=[{"id": "vid-1", "url": "https://youtube.test/vid-1", "title": "AI agents tutorial"}],
        fetch_metadata={"keyword": "ai agents"},
    )

    first = service.ingest_signal(signal, raw_payload={"video_id": "vid-1"})
    second = service.ingest_signal(signal, raw_payload={"video_id": "vid-1"})

    with fake_session_scope() as session:
        assert first["inserted"] is True
        assert second["duplicate"] is True
        assert session.query(CanonicalTrendSignal).count() == 1
        assert session.query(RawDataArchive).count() == 1


def test_save_trend_creates_evidence_and_archive(monkeypatch):
    TestingSession, fake_session_scope = _make_sqlite_session()
    monkeypatch.setattr("src.ingestion.service.session_scope", fake_session_scope)
    monkeypatch.setattr("src.scrapers.ensembledata.db_helper.session_scope", fake_session_scope)

    save_trend(
        platform="Reddit",
        topic="AI agent benchmarks",
        growth=250,
        keyword="r/artificial",
        geo="US",
        url="https://reddit.test/post-1",
        extra_data={"score": 50, "num_comments": 20, "engagement": 200},
        entity_type="post",
        entity_id="post-1",
        sampled_content_refs=[{
            "id": "post-1",
            "url": "https://reddit.test/post-1",
            "title": "AI agent benchmarks",
            "snippet": "Users compare evaluation stacks.",
        }],
        raw_payload={"id": "post-1", "title": "AI agent benchmarks"},
    )

    with fake_session_scope() as session:
        assert session.query(CanonicalTrendSignal).count() == 1
        assert session.query(TrendEvidence).count() == 1
        assert session.query(RawDataArchive).count() == 1


def test_daily_health_report_flags_anomaly(monkeypatch):
    TestingSession, fake_session_scope = _make_sqlite_session()
    monkeypatch.setattr("src.ingestion.service.session_scope", fake_session_scope)

    service = IngestionService()
    run = service.start_run("YouTube", acquisition_mode="api", country="US", language="en")
    run.fetched_count = 10
    run.parsed_count = 10
    run.inserted_count = 2
    run.deduped_count = 6
    run.failed_count = 5
    run.error_types = {"TimeoutError": 5}
    service.finish_run(run)

    report = service.daily_health_report("YouTube")
    assert len(report) == 1
    assert report[0]["anomaly"] is True
    assert report[0]["alert_state"] in {"warning", "alert"}


def test_replay_archived_payloads_returns_payload(monkeypatch):
    TestingSession, fake_session_scope = _make_sqlite_session()
    monkeypatch.setattr("src.ingestion.service.session_scope", fake_session_scope)

    service = IngestionService()
    signal = CanonicalSignalInput(
        source="News",
        entity_type="article",
        entity_id="story-1",
        label="AI agents in marketing",
        country="US",
        language="en",
        retrieved_at=datetime.utcnow(),
        granularity="day",
        metrics={"volume": 80, "growth_rate": 20},
        sampled_content_refs=[{"id": "story-1", "title": "AI agents in marketing"}],
        fetch_metadata={"keyword": "ai marketing"},
    )
    service.ingest_signal(signal, raw_payload={"id": "story-1", "headline": "AI agents in marketing"})

    rows = service.replay_archived_payloads("News", limit=5)
    assert len(rows) == 1
    assert rows[0]["payload"]["headline"] == "AI agents in marketing"


def test_google_pipeline_persists_canonical_signal(monkeypatch):
    TestingSession, fake_session_scope = _make_sqlite_session()
    monkeypatch.setattr("src.ingestion.service.session_scope", fake_session_scope)
    monkeypatch.setattr("src.scrapers.ensembledata.db_helper.session_scope", fake_session_scope)
    monkeypatch.setattr("src.scrapers.google_trends_scraper.google_trends.pipelines.get_session", lambda: TestingSession())

    pipeline = DatabasePipeline()

    class Spider:
        name = "trending_now"
        geo = "US"

    pipeline.open_spider(Spider())
    pipeline.process_item(
        {
            "keyword": "Trending Daily",
            "geo": "US",
            "data_type": "trending_searches",
            "extracted_at": datetime.utcnow(),
            "results": [
                {
                    "query": "ai video editors",
                    "traffic": "200K+",
                    "url": "https://trends.google.test/topic",
                }
            ],
        },
        Spider(),
    )
    pipeline.close_spider(Spider())

    with fake_session_scope() as session:
        assert session.query(CanonicalTrendSignal).count() == 1
        row = session.query(CanonicalTrendSignal).first()
        assert row.source == "Google Trends"
        assert row.entity_type == "topic"
