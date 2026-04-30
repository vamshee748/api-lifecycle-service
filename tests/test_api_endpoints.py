# Basic tests for API endpoints
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from app.main import app
from app.schemas import APICreate, APIStatusEnum


@pytest.fixture
def client():
    """Test client fixture"""
    return TestClient(app)


@pytest.fixture
def mock_db():
    """Mock database session"""
    return MagicMock()


def test_root_endpoint(client):
    """Test root endpoint returns expected message"""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "API Lifecycle Service is running"}


def test_health_endpoint(client):
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


@patch("app.routes.api.get_db")
@patch("app.routes.api.create_api")
def test_create_api_endpoint_success(mock_create_api, mock_get_db, client):
    """Test successful API creation"""
    # Mock database and service response
    mock_get_db.return_value = MagicMock()
    mock_api = MagicMock()
    mock_api.id = 1
    mock_api.name = "Test API"
    mock_api.service_name = "test-service"
    mock_api.version = "v1.0.0"
    mock_api.status = APIStatusEnum.DRAFT
    mock_api.description = "Test description"
    mock_api.base_url = None
    mock_api.spec_url = None
    mock_api.owner_team = None
    mock_api.created_at = "2026-04-30T10:00:00Z"
    mock_api.updated_at = None
    
    mock_create_api.return_value = mock_api
    
    # Test data
    api_data = {
        "name": "Test API",
        "service_name": "test-service",
        "version": "v1.0.0",
        "status": "draft"
    }
    
    response = client.post("/apis", json=api_data)
    
    # Verify response
    assert response.status_code == 201
    assert "id" in response.json()


def test_create_api_validation_error(client):
    """Test API creation with invalid data"""
    # Missing required fields
    api_data = {
        "name": "Test API"
        # Missing service_name and version
    }
    
    response = client.post("/apis", json=api_data)
    assert response.status_code == 422  # Validation error


def test_create_api_invalid_version_format(client):
    """Test API creation with invalid version format"""
    api_data = {
        "name": "Test API",
        "service_name": "test-service",
        "version": "invalid-version"  # Invalid format
    }
    
    response = client.post("/apis", json=api_data)
    assert response.status_code == 422  # Validation error
