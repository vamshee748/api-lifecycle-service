"""
Test suite for Analytics endpoints and aggregation functions.

Tests cover:
- Analytics record creation
- Analytics data retrieval with filtering
- Analytics summary aggregation
- Endpoint analytics
- Consumer analytics
- Time series analytics
- Top APIs by usage
- Error handling and edge cases
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timedelta
import json

from app.main import app
from app.db import Base, get_db
from app.models import API, APIStatus, APIUsageAnalytics


# ============================================================
# Test Database Setup
# ============================================================

SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    """Create tables before each test and drop after."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Provide a database session for direct database operations."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================
# Test Data Fixtures
# ============================================================

@pytest.fixture
def sample_api(db_session):
    """Create a sample API for testing."""
    api = API(
        name="Payment API",
        service_name="payment-service",
        version="v1.0.0",
        status=APIStatus.PUBLISHED,
        description="Payment processing API"
    )
    db_session.add(api)
    db_session.commit()
    db_session.refresh(api)
    return api


@pytest.fixture
def sample_api_2(db_session):
    """Create a second sample API for testing."""
    api = API(
        name="User API",
        service_name="user-service",
        version="v1.0.0",
        status=APIStatus.PUBLISHED,
        description="User management API"
    )
    db_session.add(api)
    db_session.commit()
    db_session.refresh(api)
    return api


@pytest.fixture
def sample_analytics_data(sample_api):
    """Sample analytics data for testing."""
    return {
        "api_id": sample_api.id,
        "endpoint": "/payments",
        "http_method": "POST",
        "request_count": 1000,
        "success_count": 980,
        "error_count": 20,
        "avg_response_time_ms": 125,
        "min_response_time_ms": 50,
        "max_response_time_ms": 500,
        "tracked_date": datetime.utcnow().isoformat(),
        "consumer_id": "client-123",
        "consumer_name": "Mobile App",
        "environment": "production",
        "region": "us-east-1",
        "status_2xx_count": 980,
        "status_4xx_count": 15,
        "status_5xx_count": 5,
        "total_request_size_bytes": 50000,
        "total_response_size_bytes": 100000
    }


@pytest.fixture
def create_multiple_analytics(db_session, sample_api):
    """Create multiple analytics records for testing."""
    base_date = datetime.utcnow()
    records = []
    
    for i in range(5):
        record = APIUsageAnalytics(
            api_id=sample_api.id,
            endpoint=f"/endpoint{i % 3}",
            http_method="GET" if i % 2 == 0 else "POST",
            request_count=1000 + (i * 100),
            success_count=900 + (i * 90),
            error_count=100 + (i * 10),
            avg_response_time_ms=100 + (i * 10),
            tracked_date=base_date - timedelta(days=i),
            consumer_id=f"client-{i % 2}",
            consumer_name=f"Consumer {i % 2}",
            environment="production",
            status_2xx_count=900 + (i * 90),
            status_4xx_count=50 + (i * 5),
            status_5xx_count=50 + (i * 5)
        )
        db_session.add(record)
        records.append(record)
    
    db_session.commit()
    return records


# ============================================================
# Test: Create Analytics Record
# ============================================================

def test_create_analytics_success(sample_analytics_data):
    """Test successful analytics record creation."""
    response = client.post("/analytics", json=sample_analytics_data)
    
    assert response.status_code == 201
    data = response.json()
    assert data["api_id"] == sample_analytics_data["api_id"]
    assert data["endpoint"] == sample_analytics_data["endpoint"]
    assert data["request_count"] == sample_analytics_data["request_count"]
    assert "id" in data
    assert "error_rate" in data
    assert "success_rate" in data
    assert data["error_rate"] == 2.0  # 20/1000 * 100
    assert data["success_rate"] == 98.0  # 980/1000 * 100


def test_create_analytics_api_not_found():
    """Test creating analytics for non-existent API."""
    data = {
        "api_id": 999,
        "endpoint": "/test",
        "request_count": 100,
        "tracked_date": datetime.utcnow().isoformat()
    }
    
    response = client.post("/analytics", json=data)
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_create_analytics_validation_error():
    """Test analytics creation with invalid data."""
    data = {
        "api_id": -1,  # Invalid: must be positive
        "request_count": -100,  # Invalid: must be non-negative
        "tracked_date": datetime.utcnow().isoformat()
    }
    
    response = client.post("/analytics", json=data)
    
    assert response.status_code == 422


# ============================================================
# Test: List Analytics Records
# ============================================================

def test_list_analytics_empty():
    """Test listing analytics when none exist."""
    response = client.get("/analytics")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["data"] == []


def test_list_analytics_with_data(create_multiple_analytics):
    """Test listing analytics with data."""
    response = client.get("/analytics")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["data"]) == 5


def test_list_analytics_with_api_filter(create_multiple_analytics, sample_api):
    """Test filtering analytics by API ID."""
    response = client.get(f"/analytics?api_id={sample_api.id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    for record in data["data"]:
        assert record["api_id"] == sample_api.id


def test_list_analytics_with_endpoint_filter(create_multiple_analytics):
    """Test filtering analytics by endpoint."""
    response = client.get("/analytics?endpoint=/endpoint0")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    for record in data["data"]:
        assert record["endpoint"] == "/endpoint0"


def test_list_analytics_with_date_range(create_multiple_analytics):
    """Test filtering analytics by date range."""
    start_date = (datetime.utcnow() - timedelta(days=3)).isoformat()
    end_date = datetime.utcnow().isoformat()
    
    response = client.get(f"/analytics?start_date={start_date}&end_date={end_date}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0


def test_list_analytics_pagination(create_multiple_analytics):
    """Test analytics list pagination."""
    response = client.get("/analytics?skip=2&limit=2")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    assert data["page"] == 2


# ============================================================
# Test: Get Specific Analytics Record
# ============================================================

def test_get_analytics_success(sample_analytics_data):
    """Test retrieving a specific analytics record."""
    create_response = client.post("/analytics", json=sample_analytics_data)
    analytics_id = create_response.json()["id"]
    
    response = client.get(f"/analytics/{analytics_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == analytics_id
    assert data["endpoint"] == sample_analytics_data["endpoint"]


def test_get_analytics_not_found():
    """Test retrieving non-existent analytics record."""
    response = client.get("/analytics/999")
    
    assert response.status_code == 404


# ============================================================
# Test: Analytics Summary
# ============================================================

def test_get_analytics_summary_empty():
    """Test analytics summary with no data."""
    response = client.get("/analytics/summary")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] == 0
    assert data["total_success"] == 0
    assert data["total_errors"] == 0


def test_get_analytics_summary_with_data(create_multiple_analytics, sample_api):
    """Test analytics summary with data."""
    response = client.get(f"/analytics/summary?api_id={sample_api.id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] > 0
    assert data["total_success"] > 0
    assert data["total_errors"] > 0
    assert "overall_error_rate" in data
    assert "overall_success_rate" in data
    assert "unique_consumers" in data
    assert "unique_endpoints" in data


def test_get_analytics_summary_with_date_filter(create_multiple_analytics):
    """Test analytics summary with date filtering."""
    start_date = (datetime.utcnow() - timedelta(days=2)).isoformat()
    
    response = client.get(f"/analytics/summary?start_date={start_date}")
    
    assert response.status_code == 200
    data = response.json()
    assert "date_range_start" in data
    assert "date_range_end" in data


# ============================================================
# Test: Endpoint Analytics
# ============================================================

def test_get_endpoint_analytics_empty():
    """Test endpoint analytics with no data."""
    response = client.get("/analytics/endpoints")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_get_endpoint_analytics_with_data(create_multiple_analytics, sample_api):
    """Test endpoint analytics with data."""
    response = client.get(f"/analytics/endpoints?api_id={sample_api.id}")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    
    for endpoint_data in data:
        assert "endpoint" in endpoint_data
        assert "request_count" in endpoint_data
        assert "error_rate" in endpoint_data
        assert endpoint_data["request_count"] > 0


def test_get_endpoint_analytics_sorted_by_usage(create_multiple_analytics):
    """Test that endpoint analytics are sorted by request count."""
    response = client.get("/analytics/endpoints")
    
    assert response.status_code == 200
    data = response.json()
    
    # Check that results are sorted by request_count descending
    if len(data) > 1:
        for i in range(len(data) - 1):
            assert data[i]["request_count"] >= data[i + 1]["request_count"]


def test_get_endpoint_analytics_with_limit(create_multiple_analytics):
    """Test endpoint analytics with limit."""
    response = client.get("/analytics/endpoints?limit=2")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 2


# ============================================================
# Test: Consumer Analytics
# ============================================================

def test_get_consumer_analytics_empty():
    """Test consumer analytics with no data."""
    response = client.get("/analytics/consumers")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_get_consumer_analytics_with_data(create_multiple_analytics, sample_api):
    """Test consumer analytics with data."""
    response = client.get(f"/analytics/consumers?api_id={sample_api.id}")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    
    for consumer_data in data:
        assert "consumer_id" in consumer_data
        assert "request_count" in consumer_data
        assert "error_rate" in consumer_data


def test_get_consumer_analytics_sorted_by_usage(create_multiple_analytics):
    """Test that consumer analytics are sorted by request count."""
    response = client.get("/analytics/consumers")
    
    assert response.status_code == 200
    data = response.json()
    
    # Check that results are sorted by request_count descending
    if len(data) > 1:
        for i in range(len(data) - 1):
            assert data[i]["request_count"] >= data[i + 1]["request_count"]


# ============================================================
# Test: Time Series Analytics
# ============================================================

def test_get_time_series_analytics_empty():
    """Test time series analytics with no data."""
    response = client.get("/analytics/timeseries")
    
    assert response.status_code == 200
    data = response.json()
    assert "data_points" in data
    assert len(data["data_points"]) == 0


def test_get_time_series_analytics_with_data(create_multiple_analytics, sample_api):
    """Test time series analytics with data."""
    response = client.get(f"/analytics/timeseries?api_id={sample_api.id}")
    
    assert response.status_code == 200
    data = response.json()
    assert "data_points" in data
    assert len(data["data_points"]) > 0
    
    for point in data["data_points"]:
        assert "timestamp" in point
        assert "request_count" in point
        assert "error_count" in point


def test_get_time_series_analytics_sorted_by_time(create_multiple_analytics):
    """Test that time series data is sorted by timestamp."""
    response = client.get("/analytics/timeseries")
    
    assert response.status_code == 200
    data = response.json()
    
    # Check that results are sorted by timestamp ascending
    if len(data["data_points"]) > 1:
        timestamps = [point["timestamp"] for point in data["data_points"]]
        assert timestamps == sorted(timestamps)


# ============================================================
# Test: Top APIs by Usage
# ============================================================

def test_get_top_apis_empty():
    """Test top APIs with no data."""
    response = client.get("/analytics/top-apis")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


def test_get_top_apis_with_data(create_multiple_analytics, sample_api, sample_api_2, db_session):
    """Test top APIs with data."""
    # Create analytics for second API
    record = APIUsageAnalytics(
        api_id=sample_api_2.id,
        endpoint="/users",
        http_method="GET",
        request_count=5000,
        success_count=4950,
        error_count=50,
        tracked_date=datetime.utcnow(),
        environment="production",
        status_2xx_count=4950,
        status_4xx_count=30,
        status_5xx_count=20
    )
    db_session.add(record)
    db_session.commit()
    
    response = client.get("/analytics/top-apis")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    
    for api_data in data:
        assert "api_id" in api_data
        assert "api_name" in api_data
        assert "total_requests" in api_data
        assert "error_rate" in api_data


def test_get_top_apis_sorted_by_requests(create_multiple_analytics, sample_api_2, db_session):
    """Test that top APIs are sorted by total requests."""
    # Create analytics for second API with higher traffic
    record = APIUsageAnalytics(
        api_id=sample_api_2.id,
        endpoint="/users",
        http_method="GET",
        request_count=10000,
        success_count=9900,
        error_count=100,
        tracked_date=datetime.utcnow(),
        environment="production",
        status_2xx_count=9900,
        status_4xx_count=50,
        status_5xx_count=50
    )
    db_session.add(record)
    db_session.commit()
    
    response = client.get("/analytics/top-apis")
    
    assert response.status_code == 200
    data = response.json()
    
    # Check that results are sorted by total_requests descending
    if len(data) > 1:
        for i in range(len(data) - 1):
            assert data[i]["total_requests"] >= data[i + 1]["total_requests"]


def test_get_top_apis_with_limit():
    """Test top APIs with limit parameter."""
    response = client.get("/analytics/top-apis?limit=5")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) <= 5


# ============================================================
# Test: Complex Scenarios
# ============================================================

def test_analytics_with_multiple_environments(db_session, sample_api):
    """Test analytics filtering by environment."""
    # Create analytics for different environments
    for env in ["production", "staging", "development"]:
        record = APIUsageAnalytics(
            api_id=sample_api.id,
            endpoint="/test",
            http_method="GET",
            request_count=1000,
            success_count=900,
            error_count=100,
            tracked_date=datetime.utcnow(),
            environment=env,
            status_2xx_count=900,
            status_4xx_count=50,
            status_5xx_count=50
        )
        db_session.add(record)
    db_session.commit()
    
    # Filter by production
    response = client.get("/analytics?environment=production")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["data"][0]["environment"] == "production"


def test_analytics_error_rate_calculation(sample_api):
    """Test that error rates are calculated correctly."""
    data = {
        "api_id": sample_api.id,
        "endpoint": "/test",
        "request_count": 1000,
        "success_count": 900,
        "error_count": 100,
        "tracked_date": datetime.utcnow().isoformat()
    }
    
    response = client.post("/analytics", json=data)
    
    assert response.status_code == 201
    result = response.json()
    assert result["error_rate"] == 10.0  # 100/1000 * 100
    assert result["success_rate"] == 90.0  # 900/1000 * 100


def test_analytics_with_zero_requests(sample_api):
    """Test analytics with zero requests (edge case)."""
    data = {
        "api_id": sample_api.id,
        "endpoint": "/test",
        "request_count": 0,
        "success_count": 0,
        "error_count": 0,
        "tracked_date": datetime.utcnow().isoformat()
    }
    
    response = client.post("/analytics", json=data)
    
    assert response.status_code == 201
    result = response.json()
    assert result["error_rate"] == 0.0
    assert result["success_rate"] == 0.0


# ============================================================
# Test: Date Range Queries
# ============================================================

def test_analytics_summary_date_range_validation(create_multiple_analytics):
    """Test analytics summary with specific date range."""
    today = datetime.utcnow()
    start_date = (today - timedelta(days=7)).isoformat()
    end_date = today.isoformat()
    
    response = client.get(f"/analytics/summary?start_date={start_date}&end_date={end_date}")
    
    assert response.status_code == 200
    data = response.json()
    assert "date_range_start" in data
    assert "date_range_end" in data


def test_endpoint_analytics_with_date_range(create_multiple_analytics):
    """Test endpoint analytics with date range."""
    today = datetime.utcnow()
    start_date = (today - timedelta(days=3)).isoformat()
    
    response = client.get(f"/analytics/endpoints?start_date={start_date}")
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
