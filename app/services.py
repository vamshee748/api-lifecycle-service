# Business logic for API lifecycle management
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from fastapi import HTTPException, status
from typing import Optional, List, Dict, Any
import logging
import json
import re

from app.models import API, APIStatus, APIChange, ChangeType, GovernancePolicy, PolicySeverity, APIUsageAnalytics
from app.schemas import (
    APICreate, APIUpdate, APIResponse, APIChangeCreate, APIChangeUpdate,
    GovernancePolicyCreate, GovernancePolicyUpdate, AnalyticsCreate, AnalyticsUpdate
)
from sqlalchemy import func, and_, or_
from datetime import datetime, timedelta
from app.utils import cached, invalidate_cache_pattern

# Configure logging
logger = logging.getLogger(__name__)


# ============================================================
# API Service Functions
# ============================================================

def create_api(db: Session, api_data: APICreate) -> API:
    """
    Create a new API record in the database.
    
    Args:
        db: Database session
        api_data: APICreate schema with API details
        
    Returns:
        Created API model instance
        
    Raises:
        HTTPException: 
            - 409 if API with same service_name and version already exists
            - 400 for validation errors
            - 500 for unexpected database errors
    """
    try:
        # Check if API with same service_name and version already exists
        existing_api = db.query(API).filter(
            API.service_name == api_data.service_name,
            API.version == api_data.version
        ).first()
        
        if existing_api:
            logger.warning(
                f"Attempted to create duplicate API: {api_data.service_name} v{api_data.version}"
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"API with service_name '{api_data.service_name}' and version '{api_data.version}' already exists"
            )
        
        # Create new API instance
        db_api = API(
            name=api_data.name,
            service_name=api_data.service_name,
            version=api_data.version,
            status=api_data.status,
            description=api_data.description,
            base_url=api_data.base_url,
            spec_url=api_data.spec_url,
            owner_team=api_data.owner_team
        )
        
        # Add to database
        db.add(db_api)
        db.commit()
        db.refresh(db_api)
        
        logger.info(
            f"Successfully created API: {db_api.name} (ID: {db_api.id}, "
            f"Service: {db_api.service_name}, Version: {db_api.version})"
        )
        
        return db_api
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 409 conflict)
        raise
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error creating API: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database integrity constraint violated. Please check your input data."
        )
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating API: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred"
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error creating API: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )


def get_api(db: Session, api_id: int) -> Optional[API]:
    """
    Retrieve an API by ID.
    
    Args:
        db: Database session
        api_id: API ID to retrieve
        
    Returns:
        API model instance if found, None otherwise
    """
    return db.query(API).filter(API.id == api_id).first()


def get_apis(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    status_filter: Optional[APIStatus] = None
) -> List[API]:
    """
    Retrieve a list of APIs with optional filtering and pagination.
    
    Args:
        db: Database session
        skip: Number of records to skip (for pagination)
        limit: Maximum number of records to return
        status_filter: Optional status filter
        
    Returns:
        List of API model instances
    """
    query = db.query(API)
    
    if status_filter:
        query = query.filter(API.status == status_filter)
    
    return query.offset(skip).limit(limit).all()


def update_api(db: Session, api_id: int, api_data: APIUpdate) -> Optional[API]:
    """
    Update an existing API record with validation.
    
    Args:
        db: Database session
        api_id: API ID to update
        api_data: APIUpdate schema with fields to update
        
    Returns:
        Updated API model instance if found, None otherwise
        
    Raises:
        HTTPException: 
            - 404 if API not found
            - 409 if update causes duplicate service_name + version
            - 400 for validation errors
            - 500 for unexpected database errors
    """
    try:
        db_api = get_api(db, api_id)
        
        if not db_api:
            return None
        
        # Get only the fields that are being updated
        update_data = api_data.model_dump(exclude_unset=True)
        
        if not update_data:
            logger.warning(f"Update called for API {api_id} with no fields to update")
            return db_api
        
        # Check for duplicate service_name + version if either is being updated
        if 'service_name' in update_data or 'version' in update_data:
            new_service_name = update_data.get('service_name', db_api.service_name)
            new_version = update_data.get('version', db_api.version)
            
            # Only check if the combination is actually changing
            if new_service_name != db_api.service_name or new_version != db_api.version:
                existing_api = db.query(API).filter(
                    API.service_name == new_service_name,
                    API.version == new_version,
                    API.id != api_id  # Exclude current API
                ).first()
                
                if existing_api:
                    logger.warning(
                        f"Attempted to update API {api_id} to duplicate service_name/version: "
                        f"{new_service_name} v{new_version} (conflicts with API {existing_api.id})"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"API with service_name '{new_service_name}' and version '{new_version}' already exists"
                    )
        
        # Apply updates
        for field, value in update_data.items():
            setattr(db_api, field, value)
        
        db.commit()
        db.refresh(db_api)
        
        logger.info(
            f"Successfully updated API ID: {api_id} "
            f"(Fields: {', '.join(update_data.keys())})"
        )
        
        return db_api
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 409 conflict)
        raise
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error updating API {api_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database integrity constraint violated. Please check your input data."
        )
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating API {api_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred"
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error updating API {api_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )


def delete_api(db: Session, api_id: int) -> bool:
    """
    Delete an API record with cascade deletion of related data.
    
    This will permanently delete the API and all associated:
    - API versions
    - API changes
    - Any other related records (cascade delete)
    
    Args:
        db: Database session
        api_id: API ID to delete
        
    Returns:
        True if deleted, False if not found
        
    Raises:
        HTTPException: 
            - 500 for unexpected database errors
    """
    try:
        db_api = get_api(db, api_id)
        
        if not db_api:
            logger.warning(f"Attempted to delete non-existent API ID: {api_id}")
            return False
        
        # Log details before deletion for audit trail
        api_name = db_api.name
        api_service = db_api.service_name
        api_version = db_api.version
        api_status = db_api.status.value
        
        # Count related records that will be cascade deleted
        versions_count = db_api.versions.count()
        changes_count = db_api.changes.count()
        
        # Perform deletion (cascade will handle related records)
        db.delete(db_api)
        db.commit()
        
        logger.info(
            f"Successfully deleted API ID: {api_id} "
            f"(Name: '{api_name}', Service: '{api_service}', Version: '{api_version}', Status: '{api_status}') - "
            f"Cascade deleted {versions_count} version(s) and {changes_count} change(s)"
        )
        
        return True
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error deleting API {api_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred while deleting the API"
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error deleting API {api_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while deleting the API"
        )


# ============================================================
# API Change Service Functions
# ============================================================

def create_api_change(db: Session, change_data: APIChangeCreate) -> APIChange:
    """
    Log a new API change record.
    
    Creates a change tracking record for API version updates, new features,
    breaking changes, and other modifications for governance and audit purposes.
    
    Args:
        db: Database session
        change_data: APIChangeCreate schema with change details
        
    Returns:
        Created APIChange model instance
        
    Raises:
        HTTPException: 
            - 404 if referenced API does not exist
            - 400 for validation errors
            - 500 for unexpected database errors
    """
    try:
        # Verify that the referenced API exists
        api = get_api(db, change_data.api_id)
        if not api:
            logger.warning(f"Attempted to create change for non-existent API ID: {change_data.api_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API with ID {change_data.api_id} not found"
            )
        
        # Convert enum to model enum
        change_type_model = ChangeType[change_data.change_type.value.upper()]
        
        # Create new change record
        db_change = APIChange(
            api_id=change_data.api_id,
            from_version=change_data.from_version,
            to_version=change_data.to_version,
            change_type=change_type_model,
            description=change_data.description,
            details=change_data.details
        )
        
        # Add to database
        db.add(db_change)
        db.commit()
        db.refresh(db_change)
        
        logger.info(
            f"Successfully logged API change: ID {db_change.id} for API {api.name} "
            f"({change_data.from_version or 'initial'} -> {change_data.to_version}, "
            f"Type: {change_data.change_type.value})"
        )
        
        return db_change
        
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error creating API change: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database integrity constraint violated. Please check your input data."
        )
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating API change: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred"
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error creating API change: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )


def get_api_change(db: Session, change_id: int) -> Optional[APIChange]:
    """
    Retrieve an API change record by ID.
    
    Args:
        db: Database session
        change_id: Change ID to retrieve
        
    Returns:
        APIChange model instance if found, None otherwise
    """
    return db.query(APIChange).filter(APIChange.id == change_id).first()


def get_api_changes(
    db: Session,
    api_id: Optional[int] = None,
    change_type: Optional[ChangeType] = None,
    skip: int = 0,
    limit: int = 100
) -> List[APIChange]:
    """
    Retrieve a list of API changes with optional filtering and pagination.
    
    Args:
        db: Database session
        api_id: Optional filter by specific API
        change_type: Optional filter by change type
        skip: Number of records to skip (for pagination)
        limit: Maximum number of records to return
        
    Returns:
        List of APIChange model instances
    """
    query = db.query(APIChange)
    
    if api_id is not None:
        query = query.filter(APIChange.api_id == api_id)
    
    if change_type is not None:
        query = query.filter(APIChange.change_type == change_type)
    
    # Order by most recent first
    query = query.order_by(APIChange.created_at.desc())
    
    return query.offset(skip).limit(limit).all()


def get_changes_by_api(
    db: Session,
    api_id: int,
    skip: int = 0,
    limit: int = 100
) -> List[APIChange]:
    """
    Get all changes for a specific API.
    
    Args:
        db: Database session
        api_id: API ID to get changes for
        skip: Number of records to skip
        limit: Maximum number of records to return
        
    Returns:
        List of APIChange model instances for the specified API
    """
    return db.query(APIChange).filter(
        APIChange.api_id == api_id
    ).order_by(
        APIChange.created_at.desc()
    ).offset(skip).limit(limit).all()


def get_breaking_changes(
    db: Session,
    api_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100
) -> List[APIChange]:
    """
    Get breaking changes, optionally filtered by API.
    
    Useful for impact analysis and notification systems.
    
    Args:
        db: Database session
        api_id: Optional filter by specific API
        skip: Number of records to skip
        limit: Maximum number of records to return
        
    Returns:
        List of APIChange model instances with breaking changes
    """
    query = db.query(APIChange).filter(
        APIChange.change_type == ChangeType.BREAKING
    )
    
    if api_id is not None:
        query = query.filter(APIChange.api_id == api_id)
    
    return query.order_by(
        APIChange.created_at.desc()
    ).offset(skip).limit(limit).all()


def update_api_change(
    db: Session,
    change_id: int,
    change_data: APIChangeUpdate
) -> Optional[APIChange]:
    """
    Update an existing API change record.
    
    Args:
        db: Database session
        change_id: Change ID to update
        change_data: APIChangeUpdate schema with fields to update
        
    Returns:
        Updated APIChange model instance if found, None otherwise
        
    Raises:
        HTTPException: For database errors
    """
    try:
        db_change = get_api_change(db, change_id)
        
        if not db_change:
            return None
        
        # Get only the fields that are being updated
        update_data = change_data.model_dump(exclude_unset=True)
        
        if not update_data:
            logger.warning(f"Update called for change {change_id} with no fields to update")
            return db_change
        
        # Apply updates
        for field, value in update_data.items():
            # Convert enum if needed
            if field == 'change_type' and value is not None:
                value = ChangeType[value.value.upper()]
            setattr(db_change, field, value)
        
        db.commit()
        db.refresh(db_change)
        
        logger.info(
            f"Successfully updated API change ID: {change_id} "
            f"(Fields: {', '.join(update_data.keys())})"
        )
        
        return db_change
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating API change {change_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred"
        )


def delete_api_change(db: Session, change_id: int) -> bool:
    """
    Delete an API change record.
    
    Args:
        db: Database session
        change_id: Change ID to delete
        
    Returns:
        True if deleted, False if not found
        
    Raises:
        HTTPException: For database errors
    """
    try:
        db_change = get_api_change(db, change_id)
        
        if not db_change:
            logger.warning(f"Attempted to delete non-existent change ID: {change_id}")
            return False
        
        db.delete(db_change)
        db.commit()
        
        logger.info(f"Successfully deleted API change ID: {change_id}")
        
        return True
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error deleting API change {change_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred while deleting the change"
        )


# ============================================================
# Governance Policy Service Functions
# ============================================================

def validate_policy_rule_config(rule_type: str, rule_config: Optional[str]) -> None:
    """
    Validate policy rule configuration based on rule type.
    
    This function performs deep validation of rule configurations to ensure
    they contain the required fields and valid values for each rule type.
    
    Args:
        rule_type: The type of governance rule
        rule_config: JSON string containing rule configuration
        
    Raises:
        HTTPException: 400 if rule configuration is invalid
    """
    if not rule_config:
        return
    
    try:
        config = json.loads(rule_config)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in rule_config: {str(e)}"
        )
    
    # Validate based on rule type
    if rule_type == "approval_required":
        # Validate approval configuration
        if "approvers" not in config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="approval_required rule must specify 'approvers' list"
            )
        
        if not isinstance(config["approvers"], list) or len(config["approvers"]) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'approvers' must be a non-empty list"
            )
        
        if "min_approvals" in config:
            min_approvals = config["min_approvals"]
            if not isinstance(min_approvals, int) or min_approvals < 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="'min_approvals' must be a positive integer"
                )
            
            if min_approvals > len(config["approvers"]):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="'min_approvals' cannot exceed number of approvers"
                )
    
    elif rule_type == "naming_convention":
        # Validate naming convention patterns
        if "pattern" not in config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="naming_convention rule must specify 'pattern'"
            )
        
        # Test if pattern is a valid regex
        try:
            re.compile(config["pattern"])
        except re.error as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid regex pattern: {str(e)}"
            )
        
        # Validate optional fields
        if "field" in config:
            valid_fields = {"name", "service_name", "endpoint", "parameter"}
            if config["field"] not in valid_fields:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"'field' must be one of: {', '.join(valid_fields)}"
                )
    
    elif rule_type == "versioning_standard":
        # Validate versioning standards
        if "format" not in config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="versioning_standard rule must specify 'format'"
            )
        
        valid_formats = {"semver", "date", "sequential"}
        if config["format"] not in valid_formats:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'format' must be one of: {', '.join(valid_formats)}"
            )
        
        if config["format"] == "semver" and "prefix" in config:
            if not isinstance(config["prefix"], str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="'prefix' must be a string"
                )
    
    elif rule_type == "deprecation_period":
        # Validate deprecation period rules
        if "min_days" not in config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="deprecation_period rule must specify 'min_days'"
            )
        
        min_days = config["min_days"]
        if not isinstance(min_days, int) or min_days < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'min_days' must be a non-negative integer"
            )
        
        if "notification_channels" in config:
            if not isinstance(config["notification_channels"], list):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="'notification_channels' must be a list"
                )
    
    elif rule_type == "rate_limit":
        # Validate rate limiting rules
        if "max_requests" not in config or "time_window" not in config:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="rate_limit rule must specify 'max_requests' and 'time_window'"
            )
        
        if not isinstance(config["max_requests"], int) or config["max_requests"] < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'max_requests' must be a positive integer"
            )
        
        if not isinstance(config["time_window"], str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'time_window' must be a string (e.g., '1m', '1h', '1d')"
            )
    
    elif rule_type == "security_scan":
        # Validate security scan requirements
        valid_scanners = {"owasp", "snyk", "sonarqube", "checkmarx"}
        if "scanner" in config and config["scanner"] not in valid_scanners:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'scanner' must be one of: {', '.join(valid_scanners)}"
            )
        
        if "min_score" in config:
            if not isinstance(config["min_score"], (int, float)) or not 0 <= config["min_score"] <= 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="'min_score' must be a number between 0 and 100"
                )
    
    logger.info(f"Policy rule configuration validated successfully for rule_type: {rule_type}")


def validate_policy_against_change(
    db: Session,
    policy: GovernancePolicy,
    change: APIChange
) -> Dict[str, Any]:
    """
    Validate an API change against a governance policy.
    
    This function checks if an API change complies with a specific policy
    and returns detailed validation results.
    
    Args:
        db: Database session
        policy: Governance policy to validate against
        change: API change to validate
        
    Returns:
        Dict containing validation results:
        {
            "policy_id": int,
            "policy_name": str,
            "compliant": bool,
            "severity": str,
            "enforcement_level": str,
            "violations": List[str],
            "recommendations": List[str]
        }
    """
    result = {
        "policy_id": policy.id,
        "policy_name": policy.name,
        "compliant": True,
        "severity": policy.severity.value,
        "enforcement_level": policy.enforcement_level,
        "violations": [],
        "recommendations": []
    }
    
    # Parse rule configuration
    try:
        rule_config = json.loads(policy.rule_config) if policy.rule_config else {}
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in policy {policy.id} rule_config")
        rule_config = {}
    
    # Validate based on rule type
    if policy.rule_type == "approval_required":
        # Check if breaking changes require approval
        if change.change_type == ChangeType.BREAKING:
            result["compliant"] = False
            result["violations"].append(
                f"Breaking change requires approval from: {', '.join(rule_config.get('approvers', []))}"
            )
            min_approvals = rule_config.get("min_approvals", 1)
            result["recommendations"].append(
                f"Obtain at least {min_approvals} approval(s) before proceeding"
            )
    
    elif policy.rule_type == "versioning_standard":
        # Validate version format
        version_format = rule_config.get("format", "semver")
        to_version = change.to_version
        
        if version_format == "semver":
            pattern = r'^v?\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?$'
            if not re.match(pattern, to_version):
                result["compliant"] = False
                result["violations"].append(
                    f"Version '{to_version}' does not follow semantic versioning format"
                )
                result["recommendations"].append(
                    "Use semantic versioning format: MAJOR.MINOR.PATCH (e.g., 1.2.3 or v1.2.3)"
                )
        
        elif version_format == "date":
            pattern = r'^\d{4}\.\d{2}\.\d{2}$'
            if not re.match(pattern, to_version):
                result["compliant"] = False
                result["violations"].append(
                    f"Version '{to_version}' does not follow date-based format"
                )
                result["recommendations"].append(
                    "Use date-based format: YYYY.MM.DD (e.g., 2026.05.06)"
                )
    
    elif policy.rule_type == "naming_convention":
        # Validate naming conventions
        pattern = rule_config.get("pattern", "")
        field = rule_config.get("field", "name")
        
        # Get the API to check naming
        api = db.query(API).filter(API.id == change.api_id).first()
        if api:
            value = getattr(api, field, "")
            if pattern and not re.match(pattern, value):
                result["compliant"] = False
                result["violations"].append(
                    f"API {field} '{value}' does not match required pattern: {pattern}"
                )
                result["recommendations"].append(
                    f"Update API {field} to match the naming convention pattern"
                )
    
    elif policy.rule_type == "deprecation_period":
        # Check deprecation timing
        if change.change_type == ChangeType.BREAKING:
            min_days = rule_config.get("min_days", 90)
            result["recommendations"].append(
                f"Ensure a deprecation notice is issued at least {min_days} days before retirement"
            )
            
            channels = rule_config.get("notification_channels", ["email", "slack"])
            result["recommendations"].append(
                f"Notify stakeholders via: {', '.join(channels)}"
            )
    
    logger.info(
        f"Policy validation completed - Policy: {policy.name}, "
        f"Change ID: {change.id}, Compliant: {result['compliant']}"
    )
    
    return result


def validate_change_against_policies(
    db: Session,
    change: APIChange,
    active_only: bool = True
) -> List[Dict[str, Any]]:
    """
    Validate an API change against all applicable governance policies.
    
    Args:
        db: Database session
        change: API change to validate
        active_only: Only check active policies (default: True)
        
    Returns:
        List of validation results for each applicable policy
    """
    query = db.query(GovernancePolicy)
    
    if active_only:
        query = query.filter(GovernancePolicy.is_active == True)
    
    policies = query.all()
    
    results = []
    for policy in policies:
        validation_result = validate_policy_against_change(db, policy, change)
        results.append(validation_result)
    
    logger.info(
        f"Validated change ID {change.id} against {len(results)} policies. "
        f"Non-compliant: {sum(1 for r in results if not r['compliant'])}"
    )
    
    return results


def create_governance_policy(db: Session, policy_data: GovernancePolicyCreate) -> GovernancePolicy:
    """
    Create a new governance policy with validation.
    
    Args:
        db: Database session
        policy_data: GovernancePolicyCreate schema with policy details
        
    Returns:
        Created GovernancePolicy model instance
        
    Raises:
        HTTPException: 
            - 409 if policy with same name already exists
            - 400 for validation errors
            - 500 for unexpected database errors
    """
    try:
        # Check if policy with same name already exists
        existing_policy = db.query(GovernancePolicy).filter(
            GovernancePolicy.name == policy_data.name
        ).first()
        
        if existing_policy:
            logger.warning(f"Attempted to create duplicate policy: {policy_data.name}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Policy with name '{policy_data.name}' already exists"
            )
        
        # Validate rule configuration
        validate_policy_rule_config(policy_data.rule_type, policy_data.rule_config)
        
        # Convert severity enum to model enum
        severity_model = PolicySeverity[policy_data.severity.value.upper()]
        
        # Create new policy instance
        db_policy = GovernancePolicy(
            name=policy_data.name,
            description=policy_data.description,
            rule_type=policy_data.rule_type,
            rule_config=policy_data.rule_config,
            is_active=policy_data.is_active,
            severity=severity_model,
            category=policy_data.category,
            owner_team=policy_data.owner_team,
            enforcement_level=policy_data.enforcement_level
        )
        
        # Add to database
        db.add(db_policy)
        db.commit()
        db.refresh(db_policy)
        
        logger.info(
            f"Successfully created governance policy: {db_policy.name} "
            f"(ID: {db_policy.id}, Rule Type: {db_policy.rule_type}, "
            f"Severity: {db_policy.severity.value}, Active: {db_policy.is_active})"
        )
        
        return db_policy
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 409 conflict or 400 validation)
        raise
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error creating governance policy: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database integrity constraint violated. Check policy name uniqueness."
        )
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating governance policy: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred"
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error creating governance policy: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )


def get_governance_policy(db: Session, policy_id: int) -> Optional[GovernancePolicy]:
    """
    Retrieve a governance policy by ID.
    
    Args:
        db: Database session
        policy_id: Policy ID to retrieve
        
    Returns:
        GovernancePolicy model instance if found, None otherwise
    """
    return db.query(GovernancePolicy).filter(GovernancePolicy.id == policy_id).first()


def get_governance_policies(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    active_only: Optional[bool] = None,
    category: Optional[str] = None,
    rule_type: Optional[str] = None,
    severity: Optional[PolicySeverity] = None
) -> List[GovernancePolicy]:
    """
    Retrieve a list of governance policies with optional filtering and pagination.
    
    Args:
        db: Database session
        skip: Number of records to skip (for pagination)
        limit: Maximum number of records to return
        active_only: Filter by active status (None = all, True = active, False = inactive)
        category: Optional category filter
        rule_type: Optional rule type filter
        severity: Optional severity filter
        
    Returns:
        List of GovernancePolicy model instances
    """
    query = db.query(GovernancePolicy)
    
    # Apply filters
    if active_only is not None:
        query = query.filter(GovernancePolicy.is_active == active_only)
    
    if category:
        query = query.filter(GovernancePolicy.category == category)
    
    if rule_type:
        query = query.filter(GovernancePolicy.rule_type == rule_type)
    
    if severity:
        query = query.filter(GovernancePolicy.severity == severity)
    
    # Order by severity (critical first), then by name
    query = query.order_by(
        GovernancePolicy.severity.desc(),
        GovernancePolicy.name.asc()
    )
    
    return query.offset(skip).limit(limit).all()


def update_governance_policy(
    db: Session,
    policy_id: int,
    policy_data: GovernancePolicyUpdate
) -> Optional[GovernancePolicy]:
    """
    Update an existing governance policy with validation.
    
    Args:
        db: Database session
        policy_id: Policy ID to update
        policy_data: GovernancePolicyUpdate schema with fields to update
        
    Returns:
        Updated GovernancePolicy model instance if found, None otherwise
        
    Raises:
        HTTPException: 
            - 404 if policy not found
            - 409 if update causes duplicate name
            - 400 for validation errors
            - 500 for unexpected database errors
    """
    try:
        db_policy = get_governance_policy(db, policy_id)
        
        if not db_policy:
            return None
        
        # Get only the fields that are being updated
        update_data = policy_data.model_dump(exclude_unset=True)
        
        if not update_data:
            logger.warning(f"Update called for policy {policy_id} with no fields to update")
            return db_policy
        
        # Check for duplicate name if name is being updated
        if 'name' in update_data and update_data['name'] != db_policy.name:
            existing_policy = db.query(GovernancePolicy).filter(
                GovernancePolicy.name == update_data['name'],
                GovernancePolicy.id != policy_id
            ).first()
            
            if existing_policy:
                logger.warning(
                    f"Attempted to update policy {policy_id} to duplicate name: "
                    f"{update_data['name']} (conflicts with policy {existing_policy.id})"
                )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Policy with name '{update_data['name']}' already exists"
                )
        
        # Validate rule configuration if being updated
        rule_type_to_validate = update_data.get('rule_type', db_policy.rule_type)
        rule_config_to_validate = update_data.get('rule_config', db_policy.rule_config)
        
        if 'rule_type' in update_data or 'rule_config' in update_data:
            validate_policy_rule_config(rule_type_to_validate, rule_config_to_validate)
        
        # Convert severity enum if provided
        if 'severity' in update_data:
            update_data['severity'] = PolicySeverity[update_data['severity'].value.upper()]
        
        # Apply updates
        for field, value in update_data.items():
            setattr(db_policy, field, value)
        
        db.commit()
        db.refresh(db_policy)
        
        logger.info(
            f"Successfully updated governance policy ID: {policy_id} "
            f"(Fields: {', '.join(update_data.keys())})"
        )
        
        return db_policy
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 409 conflict or 400 validation)
        raise
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error updating governance policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Database integrity constraint violated. Check policy name uniqueness."
        )
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating governance policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred"
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Unexpected error updating governance policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred"
        )


def delete_governance_policy(db: Session, policy_id: int) -> bool:
    """
    Delete a governance policy.
    
    Args:
        db: Database session
        policy_id: Policy ID to delete
        
    Returns:
        True if deleted, False if not found
        
    Raises:
        HTTPException: For database errors
    """
    try:
        db_policy = get_governance_policy(db, policy_id)
        
        if not db_policy:
            logger.warning(f"Attempted to delete non-existent policy ID: {policy_id}")
            return False
        
        # Log details before deletion for audit trail
        policy_name = db_policy.name
        policy_rule_type = db_policy.rule_type
        policy_active = db_policy.is_active
        
        db.delete(db_policy)
        db.commit()
        
        logger.info(
            f"Successfully deleted governance policy ID: {policy_id} "
            f"(Name: '{policy_name}', Rule Type: '{policy_rule_type}', Active: {policy_active})"
        )
        
        return True
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error deleting governance policy {policy_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred while deleting the policy"
        )


def toggle_policy_status(db: Session, policy_id: int, is_active: bool) -> Optional[GovernancePolicy]:
    """
    Toggle the active status of a governance policy.
    
    This is a convenience function for enabling/disabling policies without
    a full update operation.
    
    Args:
        db: Database session
        policy_id: Policy ID to toggle
        is_active: New active status
        
    Returns:
        Updated GovernancePolicy if found, None otherwise
        
    Raises:
        HTTPException: For database errors
    """
    try:
        db_policy = get_governance_policy(db, policy_id)
        
        if not db_policy:
            return None
        
        old_status = db_policy.is_active
        db_policy.is_active = is_active
        
        db.commit()
        db.refresh(db_policy)
        
        logger.info(
            f"Toggled policy ID: {policy_id} status from {old_status} to {is_active}"
        )
        
        return db_policy
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error toggling policy {policy_id} status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred"
        )


# ============================================================
# Analytics Service Functions
# ============================================================

def create_analytics_record(db: Session, analytics_data: AnalyticsCreate) -> APIUsageAnalytics:
    """
    Create a new analytics record for API usage tracking.
    
    Args:
        db: Database session
        analytics_data: AnalyticsCreate schema with usage metrics
        
    Returns:
        Created APIUsageAnalytics model instance
        
    Raises:
        HTTPException: 
            - 404 if referenced API not found
            - 400 for validation errors
            - 500 for unexpected database errors
    """
    try:
        # Verify API exists
        api = db.query(API).filter(API.id == analytics_data.api_id).first()
        if not api:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API with ID {analytics_data.api_id} not found"
            )
        
        # Create analytics record
        db_analytics = APIUsageAnalytics(
            api_id=analytics_data.api_id,
            endpoint=analytics_data.endpoint,
            http_method=analytics_data.http_method,
            request_count=analytics_data.request_count,
            success_count=analytics_data.success_count,
            error_count=analytics_data.error_count,
            avg_response_time_ms=analytics_data.avg_response_time_ms,
            min_response_time_ms=analytics_data.min_response_time_ms,
            max_response_time_ms=analytics_data.max_response_time_ms,
            tracked_date=analytics_data.tracked_date,
            consumer_id=analytics_data.consumer_id,
            consumer_name=analytics_data.consumer_name,
            environment=analytics_data.environment,
            region=analytics_data.region,
            status_2xx_count=analytics_data.status_2xx_count,
            status_4xx_count=analytics_data.status_4xx_count,
            status_5xx_count=analytics_data.status_5xx_count,
            total_request_size_bytes=analytics_data.total_request_size_bytes,
            total_response_size_bytes=analytics_data.total_response_size_bytes,
            metadata=analytics_data.metadata
        )
        
        db.add(db_analytics)
        db.commit()
        db.refresh(db_analytics)
        
        # Invalidate analytics cache after creating new record
        invalidate_cache_pattern("analytics:*")
        
        logger.info(
            f"Created analytics record: API {analytics_data.api_id}, "
            f"Endpoint: {analytics_data.endpoint}, Requests: {analytics_data.request_count}"
        )
        
        return db_analytics
        
    except HTTPException:
        raise
        
    except IntegrityError as e:
        db.rollback()
        logger.error(f"Integrity error creating analytics record: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Analytics record with this combination already exists or constraint violated"
        )
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error creating analytics record: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred"
        )


def get_analytics_record(db: Session, analytics_id: int) -> Optional[APIUsageAnalytics]:
    """
    Retrieve an analytics record by ID.
    
    Args:
        db: Database session
        analytics_id: Analytics record ID
        
    Returns:
        APIUsageAnalytics instance if found, None otherwise
    """
    return db.query(APIUsageAnalytics).filter(APIUsageAnalytics.id == analytics_id).first()


def get_analytics_records(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    api_id: Optional[int] = None,
    endpoint: Optional[str] = None,
    environment: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> List[APIUsageAnalytics]:
    """
    Retrieve analytics records with optional filtering.
    
    Args:
        db: Database session
        skip: Number of records to skip
        limit: Maximum records to return
        api_id: Filter by API ID
        endpoint: Filter by endpoint
        environment: Filter by environment
        start_date: Filter by start date
        end_date: Filter by end date
        
    Returns:
        List of APIUsageAnalytics instances
    """
    query = db.query(APIUsageAnalytics)
    
    if api_id:
        query = query.filter(APIUsageAnalytics.api_id == api_id)
    
    if endpoint:
        query = query.filter(APIUsageAnalytics.endpoint == endpoint)
    
    if environment:
        query = query.filter(APIUsageAnalytics.environment == environment)
    
    if start_date:
        query = query.filter(APIUsageAnalytics.tracked_date >= start_date)
    
    if end_date:
        query = query.filter(APIUsageAnalytics.tracked_date <= end_date)
    
    query = query.order_by(APIUsageAnalytics.tracked_date.desc())
    
    return query.offset(skip).limit(limit).all()


@cached(prefix="analytics:summary", ttl=300)
def get_analytics_summary(
    db: Session,
    api_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    environment: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get aggregated analytics summary.
    
    Cached for 5 minutes (300 seconds).
    
    Args:
        db: Database session
        api_id: Optional API ID filter
        start_date: Optional start date filter
        end_date: Optional end date filter
        environment: Optional environment filter
        
    Returns:
        Dictionary with aggregated analytics data
    """
    query = db.query(
        func.sum(APIUsageAnalytics.request_count).label('total_requests'),
        func.sum(APIUsageAnalytics.success_count).label('total_success'),
        func.sum(APIUsageAnalytics.error_count).label('total_errors'),
        func.avg(APIUsageAnalytics.avg_response_time_ms).label('avg_response_time'),
        func.count(func.distinct(APIUsageAnalytics.consumer_id)).label('unique_consumers'),
        func.count(func.distinct(APIUsageAnalytics.endpoint)).label('unique_endpoints'),
        func.min(APIUsageAnalytics.tracked_date).label('date_range_start'),
        func.max(APIUsageAnalytics.tracked_date).label('date_range_end')
    )
    
    if api_id:
        query = query.filter(APIUsageAnalytics.api_id == api_id)
    
    if start_date:
        query = query.filter(APIUsageAnalytics.tracked_date >= start_date)
    
    if end_date:
        query = query.filter(APIUsageAnalytics.tracked_date <= end_date)
    
    if environment:
        query = query.filter(APIUsageAnalytics.environment == environment)
    
    result = query.first()
    
    total_requests = result.total_requests or 0
    total_success = result.total_success or 0
    total_errors = result.total_errors or 0
    
    return {
        "api_id": api_id,
        "total_requests": total_requests,
        "total_success": total_success,
        "total_errors": total_errors,
        "avg_response_time_ms": float(result.avg_response_time) if result.avg_response_time else None,
        "overall_error_rate": (total_errors / total_requests * 100) if total_requests > 0 else 0.0,
        "overall_success_rate": (total_success / total_requests * 100) if total_requests > 0 else 0.0,
        "unique_consumers": result.unique_consumers or 0,
        "unique_endpoints": result.unique_endpoints or 0,
        "date_range_start": result.date_range_start,
        "date_range_end": result.date_range_end
    }


@cached(prefix="analytics:endpoints", ttl=300)
def get_endpoint_analytics(
    db: Session,
    api_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    environment: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get analytics aggregated by endpoint.
    
    Cached for 5 minutes (300 seconds).
    
    Args:
        db: Database session
        api_id: Optional API ID filter
        start_date: Optional start date filter
        end_date: Optional end date filter
        environment: Optional environment filter
        limit: Maximum number of endpoints to return
        
    Returns:
        List of dictionaries with per-endpoint analytics
    """
    query = db.query(
        APIUsageAnalytics.endpoint,
        APIUsageAnalytics.http_method,
        func.sum(APIUsageAnalytics.request_count).label('request_count'),
        func.sum(APIUsageAnalytics.success_count).label('success_count'),
        func.sum(APIUsageAnalytics.error_count).label('error_count'),
        func.avg(APIUsageAnalytics.avg_response_time_ms).label('avg_response_time')
    )
    
    if api_id:
        query = query.filter(APIUsageAnalytics.api_id == api_id)
    
    if start_date:
        query = query.filter(APIUsageAnalytics.tracked_date >= start_date)
    
    if end_date:
        query = query.filter(APIUsageAnalytics.tracked_date <= end_date)
    
    if environment:
        query = query.filter(APIUsageAnalytics.environment == environment)
    
    query = query.group_by(
        APIUsageAnalytics.endpoint,
        APIUsageAnalytics.http_method
    ).order_by(func.sum(APIUsageAnalytics.request_count).desc()).limit(limit)
    
    results = []
    for row in query.all():
        request_count = row.request_count or 0
        error_count = row.error_count or 0
        
        results.append({
            "endpoint": row.endpoint,
            "http_method": row.http_method,
            "request_count": request_count,
            "success_count": row.success_count or 0,
            "error_count": error_count,
            "avg_response_time_ms": float(row.avg_response_time) if row.avg_response_time else None,
            "error_rate": (error_count / request_count * 100) if request_count > 0 else 0.0
        })
    
    return results


@cached(prefix="analytics:consumers", ttl=300)
def get_consumer_analytics(
    db: Session,
    api_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    environment: Optional[str] = None,
    limit: int = 100
) -> List[Dict[str, Any]]:
    """
    Get analytics aggregated by consumer.
    
    Cached for 5 minutes (300 seconds).
    
    Args:
        db: Database session
        api_id: Optional API ID filter
        start_date: Optional start date filter
        end_date: Optional end date filter
        environment: Optional environment filter
        limit: Maximum number of consumers to return
        
    Returns:
        List of dictionaries with per-consumer analytics
    """
    query = db.query(
        APIUsageAnalytics.consumer_id,
        APIUsageAnalytics.consumer_name,
        func.sum(APIUsageAnalytics.request_count).label('request_count'),
        func.sum(APIUsageAnalytics.error_count).label('error_count')
    )
    
    if api_id:
        query = query.filter(APIUsageAnalytics.api_id == api_id)
    
    if start_date:
        query = query.filter(APIUsageAnalytics.tracked_date >= start_date)
    
    if end_date:
        query = query.filter(APIUsageAnalytics.tracked_date <= end_date)
    
    if environment:
        query = query.filter(APIUsageAnalytics.environment == environment)
    
    query = query.filter(APIUsageAnalytics.consumer_id.isnot(None))
    query = query.group_by(
        APIUsageAnalytics.consumer_id,
        APIUsageAnalytics.consumer_name
    ).order_by(func.sum(APIUsageAnalytics.request_count).desc()).limit(limit)
    
    results = []
    for row in query.all():
        request_count = row.request_count or 0
        error_count = row.error_count or 0
        
        results.append({
            "consumer_id": row.consumer_id,
            "consumer_name": row.consumer_name,
            "request_count": request_count,
            "error_count": error_count,
            "error_rate": (error_count / request_count * 100) if request_count > 0 else 0.0
        })
    
    return results


@cached(prefix="analytics:timeseries", ttl=600)
def get_time_series_analytics(
    db: Session,
    api_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    environment: Optional[str] = None,
    granularity: str = "day"
) -> List[Dict[str, Any]]:
    """
    Get time series analytics data.
    
    Cached for 10 minutes (600 seconds).
    
    Args:
        db: Database session
        api_id: Optional API ID filter
        start_date: Optional start date filter
        end_date: Optional end date filter
        environment: Optional environment filter
        granularity: Time granularity (hour, day, week, month)
        
    Returns:
        List of dictionaries with time series data points
    """
    query = db.query(
        APIUsageAnalytics.tracked_date,
        func.sum(APIUsageAnalytics.request_count).label('request_count'),
        func.sum(APIUsageAnalytics.error_count).label('error_count'),
        func.avg(APIUsageAnalytics.avg_response_time_ms).label('avg_response_time')
    )
    
    if api_id:
        query = query.filter(APIUsageAnalytics.api_id == api_id)
    
    if start_date:
        query = query.filter(APIUsageAnalytics.tracked_date >= start_date)
    
    if end_date:
        query = query.filter(APIUsageAnalytics.tracked_date <= end_date)
    
    if environment:
        query = query.filter(APIUsageAnalytics.environment == environment)
    
    query = query.group_by(APIUsageAnalytics.tracked_date).order_by(APIUsageAnalytics.tracked_date)
    
    results = []
    for row in query.all():
        results.append({
            "timestamp": row.tracked_date,
            "request_count": row.request_count or 0,
            "error_count": row.error_count or 0,
            "avg_response_time_ms": float(row.avg_response_time) if row.avg_response_time else None
        })
    
    return results


@cached(prefix="analytics:top_apis", ttl=600)
def get_top_apis_by_usage(
    db: Session,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    environment: Optional[str] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get top APIs by usage/request count.
    
    Cached for 10 minutes (600 seconds).
    
    Args:
        db: Database session
        start_date: Optional start date filter
        end_date: Optional end date filter
        environment: Optional environment filter
        limit: Number of top APIs to return
        
    Returns:
        List of dictionaries with API usage statistics
    """
    query = db.query(
        API.id,
        API.name,
        API.service_name,
        API.version,
        func.sum(APIUsageAnalytics.request_count).label('total_requests'),
        func.sum(APIUsageAnalytics.error_count).label('total_errors')
    ).join(APIUsageAnalytics, API.id == APIUsageAnalytics.api_id)
    
    if start_date:
        query = query.filter(APIUsageAnalytics.tracked_date >= start_date)
    
    if end_date:
        query = query.filter(APIUsageAnalytics.tracked_date <= end_date)
    
    if environment:
        query = query.filter(APIUsageAnalytics.environment == environment)
    
    query = query.group_by(
        API.id, API.name, API.service_name, API.version
    ).order_by(func.sum(APIUsageAnalytics.request_count).desc()).limit(limit)
    
    results = []
    for row in query.all():
        total_requests = row.total_requests or 0
        total_errors = row.total_errors or 0
        
        results.append({
            "api_id": row.id,
            "api_name": row.name,
            "service_name": row.service_name,
            "version": row.version,
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": (total_errors / total_requests * 100) if total_requests > 0 else 0.0
        })
    
    return results

