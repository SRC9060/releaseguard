import os
from dotenv import load_dotenv
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

load_dotenv()

from app.db import Base, get_db
from app.main import app

DEFAULT_TEST_DB_URL = "postgresql+psycopg://postgres@127.0.0.1:5432/releaseguard"
DB_URL = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or DEFAULT_TEST_DB_URL


@pytest.fixture(scope="session")
def engine():
    engine_kwargs = {}
    if DB_URL.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        engine_kwargs["poolclass"] = StaticPool
    else:
        engine_kwargs["pool_size"] = 25
        engine_kwargs["max_overflow"] = 50

    try:
        test_engine = create_engine(DB_URL, **engine_kwargs)
        with test_engine.connect() as conn:
            pass
        Base.metadata.create_all(bind=test_engine)
        yield test_engine
    except Exception:
        # Fallback to SQLite if PostgreSQL cannot be reached
        fallback_url = "sqlite:///./test_fallback.db"
        test_engine = create_engine(fallback_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=test_engine)
        yield test_engine
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def clean_db(engine):
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    yield


@pytest.fixture
def db_session(engine):
    TestingSessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(engine):
    TestingSessionLocal = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
    )

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

