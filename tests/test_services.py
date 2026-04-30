# Tests for service layer
import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from app.services import create_api, get_api, get_apis, update_api, delete_api
from app.schemas import APICreate, APIUpdate, APIStatusEnum
from app.models import API, APIStatus


@pytest.fixture
def mock_db():
    """Mock database session"""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


@pytest.fixture
def sample_api_data():
    """Sample API creation data"""
    return APICreate(
        name="Test API",
        service_name="test-service",
        version="v1.0.0",
        status=APIStatusEnum.DRAFT,
        description="Test description"
    )


def test_get_api_found(mock_db):
    """Test getting an existing API"""
    mock_api = MagicMock()
    mock_api.id = 1
    mock_db.query.return_value.filter.return_value.first.return_value = mock_api
    
    result = get_api(mock_db, 1)
    
    assert result == mock_api
    mock_db.query.assert_called_once()


def test_get_api_not_found(mock_db):
    """Test getting a non-existent API"""
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    result = get_api(mock_db, 999)
    
    assert result is None


def test_get_apis_with_pagination(mock_db):
    """Test getting APIs with pagination"""
    mock_apis = [MagicMock(), MagicMock(), MagicMock()]
    mock_db.query.return_value.offset.return_value.limit.return_value.all.return_value = mock_apis
    
    result = get_apis(mock_db, skip=0, limit=10)
    
    assert len(result) == 3
    mock_db.query.return_value.offset.assert_called_with(0)
    mock_db.query.return_value.offset.return_value.limit.assert_called_with(10)


def test_get_apis_with_status_filter(mock_db):
    """Test getting APIs with status filter"""
    mock_apis = [MagicMock()]
    mock_query = mock_db.query.return_value
    mock_query.filter.return_value.offset.return_value.limit.return_value.all.return_value = mock_apis
    
    result = get_apis(mock_db, skip=0, limit=10, status_filter=APIStatus.PUBLISHED)
    
    assert len(result) == 1
    mock_db.query.return_value.filter.assert_called_once()


def test_delete_api_success(mock_db):
    """Test successful API deletion"""
    mock_api = MagicMock()
    mock_api.id = 1
    mock_api.name = "Test API"
    mock_api.service_name = "test-service"
    mock_api.version = "v1.0.0"
    mock_api.status.value = "draft"
    mock_api.versions.count.return_value = 2
    mock_api.changes.count.return_value = 5
    
    mock_db.query.return_value.filter.return_value.first.return_value = mock_api
    
    result = delete_api(mock_db, 1)
    
    assert result is True
    mock_db.delete.assert_called_once_with(mock_api)
    mock_db.commit.assert_called_once()


def test_delete_api_not_found(mock_db):
    """Test deleting a non-existent API"""
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    result = delete_api(mock_db, 999)
    
    assert result is False
    mock_db.delete.assert_not_called()
