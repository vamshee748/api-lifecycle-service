"""
Test suite for Governance Policy endpoints and validation logic.

Tests cover:
- Policy CRUD operations
- Policy validation logic
- Rule configuration validation
- Change validation against policies
- Error handling and edge cases
- Production-level scenarios
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import json

from app.main import app
from app.db import Base, get_db
from app.models import GovernancePolicy, PolicySeverity, API, APIChange, ChangeType, APIStatus


# ============================================================
# Test Database Setup
# ============================================================

# Create in-memory SQLite database for testing
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

# Create test client
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
def sample_policy_data():
    """Sample policy data for testing."""
    return {
        "name": "Breaking Change Approval",
        "description": "All breaking changes require approval from architecture team",
        "rule_type": "approval_required",
        "rule_config": json.dumps({
            "approvers": ["architecture-team", "security-team"],
            "min_approvals": 2
        }),
        "is_active": True,
        "severity": "critical",
        "category": "compliance",
        "owner_team": "architecture-team",
        "enforcement_level": "blocking"
    }


@pytest.fixture
def sample_naming_policy():
    """Sample naming convention policy."""
    return {
        "name": "Service Name Convention",
        "description": "Service names must be lowercase with hyphens",
        "rule_type": "naming_convention",
        "rule_config": json.dumps({
            "pattern": "^[a-z][a-z0-9-]*$",
            "field": "service_name"
        }),
        "is_active": True,
        "severity": "warning",
        "category": "standards",
        "enforcement_level": "advisory"
    }


@pytest.fixture
def sample_versioning_policy():
    """Sample versioning standard policy."""
    return {
        "name": "Semantic Versioning",
        "description": "All versions must follow semantic versioning",
        "rule_type": "versioning_standard",
        "rule_config": json.dumps({
            "format": "semver",
            "prefix": "v"
        }),
        "is_active": True,
        "severity": "warning",
        "category": "standards",
        "enforcement_level": "advisory"
    }


@pytest.fixture
def sample_api(db_session):
    """Create a sample API for testing."""
    api = API(
        name="Test API",
        service_name="test-service",
        version="v1.0.0",
        status=APIStatus.PUBLISHED,
        description="Test API for policy validation"
    )
    db_session.add(api)
    db_session.commit()
    db_session.refresh(api)
    return api


@pytest.fixture
def sample_breaking_change(db_session, sample_api):
    """Create a sample breaking change for testing."""
    change = APIChange(
        api_id=sample_api.id,
        from_version="v1.0.0",
        to_version="v2.0.0",
        change_type=ChangeType.BREAKING,
        description="Changed payment field from string to enum",
        details=json.dumps({"field": "payment_method", "old_type": "string", "new_type": "enum"})
    )
    db_session.add(change)
    db_session.commit()
    db_session.refresh(change)
    return change


# ============================================================
# Test: Create Policy
# ============================================================

def test_create_policy_success(sample_policy_data):
    """Test successful policy creation."""
    response = client.post("/policies", json=sample_policy_data)
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == sample_policy_data["name"]
    assert data["rule_type"] == sample_policy_data["rule_type"]
    assert data["severity"] == sample_policy_data["severity"]
    assert "id" in data
    assert "created_at" in data


def test_create_policy_duplicate_name(sample_policy_data):
    """Test that duplicate policy names are rejected."""
    # Create first policy
    client.post("/policies", json=sample_policy_data)
    
    # Try to create duplicate
    response = client.post("/policies", json=sample_policy_data)
    
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"]


def test_create_policy_invalid_rule_config():
    """Test that invalid rule configuration is rejected."""
    policy_data = {
        "name": "Invalid Policy",
        "rule_type": "approval_required",
        "rule_config": json.dumps({"invalid_field": "value"}),  # Missing required 'approvers'
        "severity": "warning",
        "enforcement_level": "advisory"
    }
    
    response = client.post("/policies", json=policy_data)
    
    assert response.status_code == 400
    assert "approvers" in response.json()["detail"]


def test_create_policy_invalid_json_config():
    """Test that malformed JSON in rule_config is rejected."""
    policy_data = {
        "name": "Invalid JSON Policy",
        "rule_type": "approval_required",
        "rule_config": "not valid json{",
        "severity": "warning",
        "enforcement_level": "advisory"
    }
    
    response = client.post("/policies", json=policy_data)
    
    assert response.status_code == 422  # Validation error


def test_create_policy_with_naming_convention(sample_naming_policy):
    """Test creating a naming convention policy."""
    response = client.post("/policies", json=sample_naming_policy)
    
    assert response.status_code == 201
    data = response.json()
    assert data["rule_type"] == "naming_convention"


def test_create_policy_invalid_regex_pattern():
    """Test that invalid regex patterns are rejected."""
    policy_data = {
        "name": "Invalid Regex",
        "rule_type": "naming_convention",
        "rule_config": json.dumps({"pattern": "[invalid(regex"}),
        "severity": "warning",
        "enforcement_level": "advisory"
    }
    
    response = client.post("/policies", json=policy_data)
    
    assert response.status_code == 400
    assert "regex" in response.json()["detail"].lower()


# ============================================================
# Test: List Policies
# ============================================================

def test_list_policies_empty():
    """Test listing policies when none exist."""
    response = client.get("/policies")
    
    assert response.status_code == 200
    assert response.json() == []


def test_list_policies_with_data(sample_policy_data, sample_naming_policy):
    """Test listing policies with data."""
    client.post("/policies", json=sample_policy_data)
    client.post("/policies", json=sample_naming_policy)
    
    response = client.get("/policies")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_list_policies_filter_by_active():
    """Test filtering policies by active status."""
    # Create active policy
    policy1 = {
        "name": "Active Policy",
        "rule_type": "approval_required",
        "rule_config": json.dumps({"approvers": ["team1"]}),
        "is_active": True,
        "severity": "warning",
        "enforcement_level": "advisory"
    }
    client.post("/policies", json=policy1)
    
    # Create inactive policy
    policy2 = {
        "name": "Inactive Policy",
        "rule_type": "approval_required",
        "rule_config": json.dumps({"approvers": ["team2"]}),
        "is_active": False,
        "severity": "warning",
        "enforcement_level": "advisory"
    }
    client.post("/policies", json=policy2)
    
    # Filter for active only
    response = client.get("/policies?active_only=true")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["is_active"] is True


def test_list_policies_filter_by_severity(sample_policy_data, sample_naming_policy):
    """Test filtering policies by severity."""
    client.post("/policies", json=sample_policy_data)  # critical
    client.post("/policies", json=sample_naming_policy)  # warning
    
    response = client.get("/policies?severity=critical")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["severity"] == "critical"


def test_list_policies_filter_by_category(sample_policy_data, sample_naming_policy):
    """Test filtering policies by category."""
    client.post("/policies", json=sample_policy_data)  # compliance
    client.post("/policies", json=sample_naming_policy)  # standards
    
    response = client.get("/policies?category=compliance")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["category"] == "compliance"


def test_list_policies_pagination():
    """Test policy list pagination."""
    # Create multiple policies
    for i in range(5):
        policy = {
            "name": f"Policy {i}",
            "rule_type": "approval_required",
            "rule_config": json.dumps({"approvers": [f"team{i}"]}),
            "severity": "warning",
            "enforcement_level": "advisory"
        }
        client.post("/policies", json=policy)
    
    # Test pagination
    response = client.get("/policies?skip=2&limit=2")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


# ============================================================
# Test: Get Policy by ID
# ============================================================

def test_get_policy_success(sample_policy_data):
    """Test retrieving a policy by ID."""
    create_response = client.post("/policies", json=sample_policy_data)
    policy_id = create_response.json()["id"]
    
    response = client.get(f"/policies/{policy_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == policy_id
    assert data["name"] == sample_policy_data["name"]


def test_get_policy_not_found():
    """Test retrieving non-existent policy."""
    response = client.get("/policies/999")
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ============================================================
# Test: Update Policy
# ============================================================

def test_update_policy_success(sample_policy_data):
    """Test successful policy update."""
    create_response = client.post("/policies", json=sample_policy_data)
    policy_id = create_response.json()["id"]
    
    update_data = {
        "description": "Updated description",
        "is_active": False,
        "severity": "warning"
    }
    
    response = client.put(f"/policies/{policy_id}", json=update_data)
    
    assert response.status_code == 200
    data = response.json()
    assert data["description"] == update_data["description"]
    assert data["is_active"] == update_data["is_active"]
    assert data["severity"] == update_data["severity"]


def test_update_policy_duplicate_name(sample_policy_data):
    """Test that updating to duplicate name is rejected."""
    # Create two policies
    policy1_response = client.post("/policies", json=sample_policy_data)
    policy1_id = policy1_response.json()["id"]
    
    policy2_data = {**sample_policy_data, "name": "Another Policy"}
    policy2_response = client.post("/policies", json=policy2_data)
    policy2_id = policy2_response.json()["id"]
    
    # Try to update policy2 with policy1's name
    update_data = {"name": sample_policy_data["name"]}
    response = client.put(f"/policies/{policy2_id}", json=update_data)
    
    assert response.status_code == 409


def test_update_policy_not_found():
    """Test updating non-existent policy."""
    response = client.put("/policies/999", json={"description": "Updated"})
    
    assert response.status_code == 404


# ============================================================
# Test: Delete Policy
# ============================================================

def test_delete_policy_success(sample_policy_data):
    """Test successful policy deletion."""
    create_response = client.post("/policies", json=sample_policy_data)
    policy_id = create_response.json()["id"]
    
    response = client.delete(f"/policies/{policy_id}")
    
    assert response.status_code == 204
    
    # Verify policy is deleted
    get_response = client.get(f"/policies/{policy_id}")
    assert get_response.status_code == 404


def test_delete_policy_not_found():
    """Test deleting non-existent policy."""
    response = client.delete("/policies/999")
    
    assert response.status_code == 404


# ============================================================
# Test: Toggle Policy Status
# ============================================================

def test_toggle_policy_status_success(sample_policy_data):
    """Test toggling policy active status."""
    create_response = client.post("/policies", json=sample_policy_data)
    policy_id = create_response.json()["id"]
    
    # Toggle to inactive
    response = client.patch(f"/policies/{policy_id}/toggle?is_active=false")
    
    assert response.status_code == 200
    data = response.json()
    assert data["is_active"] is False
    
    # Toggle back to active
    response = client.patch(f"/policies/{policy_id}/toggle?is_active=true")
    
    assert response.status_code == 200
    data = response.json()
    assert data["is_active"] is True


def test_toggle_policy_not_found():
    """Test toggling non-existent policy."""
    response = client.patch("/policies/999/toggle?is_active=true")
    
    assert response.status_code == 404


# ============================================================
# Test: Validate Change Against Policies
# ============================================================

def test_validate_change_success(sample_policy_data, sample_breaking_change, db_session):
    """Test validating a change against policies."""
    # Create policy
    client.post("/policies", json=sample_policy_data)
    
    # Validate change
    response = client.post(f"/policies/validate/change/{sample_breaking_change.id}")
    
    assert response.status_code == 200
    data = response.json()
    assert "validation_results" in data
    assert data["change_id"] == sample_breaking_change.id
    assert data["total_policies_checked"] >= 1
    assert "total_violations" in data
    assert "blocking_violations" in data


def test_validate_change_not_found():
    """Test validating non-existent change."""
    response = client.post("/policies/validate/change/999")
    
    assert response.status_code == 404


def test_validate_breaking_change_requires_approval(sample_policy_data, sample_breaking_change, db_session):
    """Test that breaking changes require approval."""
    # Create approval policy
    client.post("/policies", json=sample_policy_data)
    
    # Validate breaking change
    response = client.post(f"/policies/validate/change/{sample_breaking_change.id}")
    
    data = response.json()
    validation_results = data["validation_results"]
    
    # Should have at least one validation result
    assert len(validation_results) > 0
    
    # Check for approval requirement violation
    approval_result = next(
        (r for r in validation_results if r["policy_name"] == "Breaking Change Approval"),
        None
    )
    assert approval_result is not None
    assert approval_result["compliant"] is False
    assert "approval" in approval_result["violations"][0].lower()


# ============================================================
# Test: Policy Statistics
# ============================================================

def test_get_policy_statistics_empty():
    """Test statistics with no policies."""
    response = client.get("/policies/statistics/summary")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total_policies"] == 0
    assert data["active_policies"] == 0


def test_get_policy_statistics_with_data(sample_policy_data, sample_naming_policy):
    """Test statistics with policies."""
    client.post("/policies", json=sample_policy_data)
    client.post("/policies", json=sample_naming_policy)
    
    response = client.get("/policies/statistics/summary")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total_policies"] == 2
    assert data["active_policies"] == 2
    assert "severity_breakdown" in data
    assert "category_breakdown" in data
    assert "rule_type_breakdown" in data
    assert "enforcement_breakdown" in data


# ============================================================
# Test: Rule Validation Logic
# ============================================================

def test_versioning_standard_validation(sample_versioning_policy, sample_breaking_change, db_session):
    """Test versioning standard validation."""
    # Create versioning policy
    client.post("/policies", json=sample_versioning_policy)
    
    # Validate change (should pass as it uses semver)
    response = client.post(f"/policies/validate/change/{sample_breaking_change.id}")
    
    data = response.json()
    versioning_result = next(
        (r for r in data["validation_results"] if r["policy_name"] == "Semantic Versioning"),
        None
    )
    assert versioning_result is not None


def test_deprecation_period_minimum_days():
    """Test deprecation period rule configuration validation."""
    policy_data = {
        "name": "Deprecation Policy",
        "rule_type": "deprecation_period",
        "rule_config": json.dumps({"min_days": 90}),
        "severity": "warning",
        "enforcement_level": "advisory"
    }
    
    response = client.post("/policies", json=policy_data)
    
    assert response.status_code == 201


def test_rate_limit_validation():
    """Test rate limit rule configuration validation."""
    policy_data = {
        "name": "Rate Limit Policy",
        "rule_type": "rate_limit",
        "rule_config": json.dumps({
            "max_requests": 1000,
            "time_window": "1m"
        }),
        "severity": "warning",
        "enforcement_level": "monitoring"
    }
    
    response = client.post("/policies", json=policy_data)
    
    assert response.status_code == 201


def test_security_scan_validation():
    """Test security scan rule configuration validation."""
    policy_data = {
        "name": "Security Scan Policy",
        "rule_type": "security_scan",
        "rule_config": json.dumps({
            "scanner": "sonarqube",
            "min_score": 80
        }),
        "severity": "critical",
        "enforcement_level": "blocking"
    }
    
    response = client.post("/policies", json=policy_data)
    
    assert response.status_code == 201


# ============================================================
# Test: Edge Cases
# ============================================================

def test_create_policy_with_empty_rule_config():
    """Test creating a policy with empty rule config."""
    policy_data = {
        "name": "No Config Policy",
        "rule_type": "approval_required",
        "rule_config": None,
        "severity": "info",
        "enforcement_level": "monitoring"
    }
    
    response = client.post("/policies", json=policy_data)
    
    # Should be rejected as approval_required needs config
    assert response.status_code == 400


def test_update_policy_empty_update():
    """Test updating policy with no fields."""
    policy_data = {
        "name": "Test Policy",
        "rule_type": "approval_required",
        "rule_config": json.dumps({"approvers": ["team1"]}),
        "severity": "warning",
        "enforcement_level": "advisory"
    }
    create_response = client.post("/policies", json=policy_data)
    policy_id = create_response.json()["id"]
    
    # Update with no fields
    response = client.put(f"/policies/{policy_id}", json={})
    
    # Should still return the policy unchanged
    assert response.status_code == 200


def test_validate_against_inactive_policies(sample_policy_data, sample_breaking_change, db_session):
    """Test validation with inactive policies."""
    # Create inactive policy
    policy_data = {**sample_policy_data, "is_active": False}
    client.post("/policies", json=policy_data)
    
    # Validate with active_only=true (default)
    response = client.post(f"/policies/validate/change/{sample_breaking_change.id}?active_only=true")
    
    data = response.json()
    # Should not check inactive policies
    assert data["total_policies_checked"] == 0
    
    # Validate with active_only=false
    response = client.post(f"/policies/validate/change/{sample_breaking_change.id}?active_only=false")
    
    data = response.json()
    # Should check inactive policies
    assert data["total_policies_checked"] >= 1
