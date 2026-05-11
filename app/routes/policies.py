# Governance Policy routes - Endpoints for managing governance policies
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db import get_db
from app.schemas import (
    GovernancePolicyCreate, 
    GovernancePolicyUpdate, 
    GovernancePolicyResponse,
    SeverityEnum
)
from app.services import (
    create_governance_policy,
    get_governance_policy,
    get_governance_policies,
    update_governance_policy,
    delete_governance_policy,
    toggle_policy_status,
    validate_change_against_policies
)
from app.models import PolicySeverity, GovernancePolicy, APIChange

# Create router for governance policy endpoints
router = APIRouter(
    prefix="/policies",
    tags=["Policies"],
    responses={
        404: {"description": "Policy not found"},
        500: {"description": "Internal server error"}
    }
)


@router.post(
    "",
    response_model=GovernancePolicyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new governance policy",
    description="Create a governance policy to enforce API lifecycle rules and compliance requirements",
    responses={
        201: {"description": "Policy successfully created"},
        400: {"description": "Invalid request data or rule configuration"},
        409: {"description": "Policy with same name already exists"},
        422: {"description": "Validation error"}
    }
)
def create_policy_endpoint(
    policy_data: GovernancePolicyCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new governance policy with comprehensive validation.
    
    **Request Body:**
    - **name**: Unique name for the policy (required)
    - **description**: Detailed description of the policy's purpose (optional)
    - **rule_type**: Type of governance rule (required)
      - approval_required: Requires approval for changes
      - naming_convention: Enforces naming standards
      - versioning_standard: Enforces version format
      - deprecation_period: Enforces minimum deprecation period
      - rate_limit: Enforces rate limiting
      - security_scan: Requires security scanning
    - **rule_config**: JSON configuration for the rule (optional but recommended)
    - **is_active**: Whether the policy is active (default: true)
    - **severity**: Severity level - critical, warning, or info (default: warning)
    - **category**: Policy category (e.g., security, compliance, standards) (optional)
    - **owner_team**: Team responsible for the policy (optional)
    - **enforcement_level**: blocking, advisory, or monitoring (default: advisory)
    
    **Rule Configuration Examples:**
    
    *Approval Required:*
    ```json
    {
      "approvers": ["architecture-team", "security-team"],
      "min_approvals": 2
    }
    ```
    
    *Naming Convention:*
    ```json
    {
      "pattern": "^[a-z][a-z0-9-]*$",
      "field": "service_name"
    }
    ```
    
    *Versioning Standard:*
    ```json
    {
      "format": "semver",
      "prefix": "v"
    }
    ```
    
    *Deprecation Period:*
    ```json
    {
      "min_days": 90,
      "notification_channels": ["email", "slack"]
    }
    ```
    
    **Returns:**
    - Complete policy record including generated ID and timestamps
    
    **Errors:**
    - 409: If a policy with the same name already exists
    - 400: If rule configuration is invalid for the specified rule type
    - 422: If request data fails validation
    """
    return create_governance_policy(db=db, policy_data=policy_data)


@router.get(
    "",
    response_model=List[GovernancePolicyResponse],
    summary="List governance policies",
    description="Retrieve a list of governance policies with optional filtering and pagination",
    responses={
        200: {"description": "List of policies successfully retrieved"}
    }
)
def list_policies_endpoint(
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    active_only: Optional[bool] = Query(None, description="Filter by active status (true/false, omit for all)"),
    category: Optional[str] = Query(None, description="Filter by category"),
    rule_type: Optional[str] = Query(None, description="Filter by rule type"),
    severity: Optional[SeverityEnum] = Query(None, description="Filter by severity level"),
    db: Session = Depends(get_db)
):
    """
    Retrieve a list of governance policies with comprehensive filtering.
    
    **Query Parameters:**
    - **skip**: Number of records to skip (for pagination, default: 0)
    - **limit**: Maximum number of records to return (default: 100, max: 1000)
    - **active_only**: Filter by active status
      - true: Only active policies
      - false: Only inactive policies
      - omit: All policies
    - **category**: Filter by policy category (e.g., "security", "compliance")
    - **rule_type**: Filter by rule type (e.g., "approval_required", "naming_convention")
    - **severity**: Filter by severity level (critical, warning, info)
    
    **Returns:**
    - List of policies ordered by severity (critical first) and name
    
    **Examples:**
    - GET /policies?active_only=true&severity=critical
    - GET /policies?category=security&rule_type=approval_required
    - GET /policies?skip=10&limit=50
    """
    # Convert severity enum to model enum if provided
    severity_model = None
    if severity:
        severity_model = PolicySeverity[severity.value.upper()]
    
    policies = get_governance_policies(
        db=db,
        skip=skip,
        limit=limit,
        active_only=active_only,
        category=category,
        rule_type=rule_type,
        severity=severity_model
    )
    
    return policies


@router.get(
    "/{policy_id}",
    response_model=GovernancePolicyResponse,
    summary="Get a specific governance policy",
    description="Retrieve detailed information about a specific governance policy by ID",
    responses={
        200: {"description": "Policy successfully retrieved"},
        404: {"description": "Policy not found"}
    }
)
def get_policy_endpoint(
    policy_id: int = Path(..., gt=0, description="ID of the policy to retrieve"),
    db: Session = Depends(get_db)
):
    """
    Retrieve a specific governance policy by ID.
    
    **Path Parameters:**
    - **policy_id**: Unique identifier of the policy (must be positive integer)
    
    **Returns:**
    - Complete policy record including all fields and timestamps
    
    **Errors:**
    - 404: If policy with the specified ID does not exist
    """
    db_policy = get_governance_policy(db=db, policy_id=policy_id)
    
    if db_policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy with ID {policy_id} not found"
        )
    
    return db_policy


@router.put(
    "/{policy_id}",
    response_model=GovernancePolicyResponse,
    summary="Update a governance policy",
    description="Update an existing governance policy with validation",
    responses={
        200: {"description": "Policy successfully updated"},
        400: {"description": "Invalid request data or rule configuration"},
        404: {"description": "Policy not found"},
        409: {"description": "Update causes name conflict"},
        422: {"description": "Validation error"}
    }
)
def update_policy_endpoint(
    policy_id: int = Path(..., gt=0, description="ID of the policy to update"),
    policy_data: GovernancePolicyUpdate = ...,
    db: Session = Depends(get_db)
):
    """
    Update an existing governance policy.
    
    **Path Parameters:**
    - **policy_id**: Unique identifier of the policy to update
    
    **Request Body:**
    - All fields are optional; only provided fields will be updated
    - **name**: Unique name for the policy
    - **description**: Detailed description of the policy
    - **rule_type**: Type of governance rule
    - **rule_config**: JSON configuration for the rule
    - **is_active**: Whether the policy is active
    - **severity**: Severity level (critical, warning, info)
    - **category**: Policy category
    - **owner_team**: Team responsible for the policy
    - **enforcement_level**: blocking, advisory, or monitoring
    
    **Returns:**
    - Updated policy record with all fields and timestamps
    
    **Errors:**
    - 404: If policy with the specified ID does not exist
    - 409: If updating the name causes a conflict with an existing policy
    - 400: If rule configuration is invalid for the specified rule type
    - 422: If request data fails validation
    
    **Note:** When updating rule_type or rule_config, the configuration will be
    re-validated to ensure consistency.
    """
    db_policy = update_governance_policy(db=db, policy_id=policy_id, policy_data=policy_data)
    
    if db_policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy with ID {policy_id} not found"
        )
    
    return db_policy


@router.delete(
    "/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a governance policy",
    description="Permanently delete a governance policy",
    responses={
        204: {"description": "Policy successfully deleted"},
        404: {"description": "Policy not found"}
    }
)
def delete_policy_endpoint(
    policy_id: int = Path(..., gt=0, description="ID of the policy to delete"),
    db: Session = Depends(get_db)
):
    """
    Permanently delete a governance policy.
    
    **Path Parameters:**
    - **policy_id**: Unique identifier of the policy to delete
    
    **Returns:**
    - 204 No Content on successful deletion
    
    **Errors:**
    - 404: If policy with the specified ID does not exist
    
    **Warning:** This operation cannot be undone. Consider deactivating the policy
    instead of deleting it to preserve audit history.
    """
    deleted = delete_governance_policy(db=db, policy_id=policy_id)
    
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy with ID {policy_id} not found"
        )
    
    return None


@router.patch(
    "/{policy_id}/toggle",
    response_model=GovernancePolicyResponse,
    summary="Toggle policy active status",
    description="Enable or disable a governance policy",
    responses={
        200: {"description": "Policy status successfully toggled"},
        404: {"description": "Policy not found"}
    }
)
def toggle_policy_endpoint(
    policy_id: int = Path(..., gt=0, description="ID of the policy to toggle"),
    is_active: bool = Query(..., description="New active status (true to enable, false to disable)"),
    db: Session = Depends(get_db)
):
    """
    Toggle the active status of a governance policy.
    
    This endpoint provides a convenient way to enable or disable policies
    without needing to perform a full update operation.
    
    **Path Parameters:**
    - **policy_id**: Unique identifier of the policy to toggle
    
    **Query Parameters:**
    - **is_active**: New active status
      - true: Enable/activate the policy
      - false: Disable/deactivate the policy
    
    **Returns:**
    - Updated policy record with new active status
    
    **Errors:**
    - 404: If policy with the specified ID does not exist
    
    **Use Cases:**
    - Temporarily disable a policy for testing or maintenance
    - Enable a policy after review and approval
    - Quick enable/disable without modifying other policy fields
    """
    db_policy = toggle_policy_status(db=db, policy_id=policy_id, is_active=is_active)
    
    if db_policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Policy with ID {policy_id} not found"
        )
    
    return db_policy


@router.post(
    "/validate/change/{change_id}",
    summary="Validate API change against policies",
    description="Validate an API change against all active governance policies",
    responses={
        200: {"description": "Validation completed successfully"},
        404: {"description": "API change not found"}
    }
)
def validate_change_endpoint(
    change_id: int = Path(..., gt=0, description="ID of the API change to validate"),
    active_only: bool = Query(True, description="Only validate against active policies"),
    db: Session = Depends(get_db)
):
    """
    Validate an API change against governance policies.
    
    This endpoint checks if an API change complies with all applicable
    governance policies and returns detailed validation results.
    
    **Path Parameters:**
    - **change_id**: ID of the API change to validate
    
    **Query Parameters:**
    - **active_only**: Only validate against active policies (default: true)
    
    **Returns:**
    - List of validation results for each applicable policy:
      ```json
      [
        {
          "policy_id": 1,
          "policy_name": "Breaking Change Approval",
          "compliant": false,
          "severity": "critical",
          "enforcement_level": "blocking",
          "violations": ["Breaking change requires approval from: architecture-team"],
          "recommendations": ["Obtain at least 2 approval(s) before proceeding"]
        }
      ]
      ```
    
    **Errors:**
    - 404: If the specified API change does not exist
    
    **Use Cases:**
    - Pre-deployment validation of API changes
    - Compliance checking and reporting
    - CI/CD pipeline integration for automated governance
    - Identifying policy violations before merging changes
    """
    # Check if change exists
    db_change = db.query(APIChange).filter(APIChange.id == change_id).first()
    
    if db_change is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API change with ID {change_id} not found"
        )
    
    # Validate against policies
    validation_results = validate_change_against_policies(
        db=db,
        change=db_change,
        active_only=active_only
    )
    
    return {
        "change_id": change_id,
        "api_id": db_change.api_id,
        "from_version": db_change.from_version,
        "to_version": db_change.to_version,
        "change_type": db_change.change_type.value,
        "validation_results": validation_results,
        "total_policies_checked": len(validation_results),
        "total_violations": sum(1 for r in validation_results if not r["compliant"]),
        "blocking_violations": sum(
            1 for r in validation_results 
            if not r["compliant"] and r["enforcement_level"] == "blocking"
        )
    }


@router.get(
    "/statistics/summary",
    summary="Get policy statistics",
    description="Retrieve summary statistics about governance policies",
    responses={
        200: {"description": "Statistics successfully retrieved"}
    }
)
def get_policy_statistics_endpoint(
    db: Session = Depends(get_db)
):
    """
    Get summary statistics about governance policies.
    
    **Returns:**
    - Statistics including:
      - Total number of policies
      - Number of active policies
      - Breakdown by severity level
      - Breakdown by category
      - Breakdown by rule type
      - Breakdown by enforcement level
    
    **Use Cases:**
    - Dashboard and reporting
    - Policy governance oversight
    - Compliance reporting
    """
    total_policies = db.query(GovernancePolicy).count()
    active_policies = db.query(GovernancePolicy).filter(GovernancePolicy.is_active == True).count()
    
    # Breakdown by severity
    severity_breakdown = {}
    for severity in PolicySeverity:
        count = db.query(GovernancePolicy).filter(
            GovernancePolicy.severity == severity,
            GovernancePolicy.is_active == True
        ).count()
        severity_breakdown[severity.value] = count
    
    # Breakdown by category
    categories = db.query(GovernancePolicy.category).distinct().all()
    category_breakdown = {}
    for (category,) in categories:
        if category:
            count = db.query(GovernancePolicy).filter(
                GovernancePolicy.category == category,
                GovernancePolicy.is_active == True
            ).count()
            category_breakdown[category] = count
    
    # Breakdown by rule type
    rule_types = db.query(GovernancePolicy.rule_type).distinct().all()
    rule_type_breakdown = {}
    for (rule_type,) in rule_types:
        count = db.query(GovernancePolicy).filter(
            GovernancePolicy.rule_type == rule_type,
            GovernancePolicy.is_active == True
        ).count()
        rule_type_breakdown[rule_type] = count
    
    # Breakdown by enforcement level
    enforcement_levels = db.query(GovernancePolicy.enforcement_level).distinct().all()
    enforcement_breakdown = {}
    for (enforcement_level,) in enforcement_levels:
        count = db.query(GovernancePolicy).filter(
            GovernancePolicy.enforcement_level == enforcement_level,
            GovernancePolicy.is_active == True
        ).count()
        enforcement_breakdown[enforcement_level] = count
    
    return {
        "total_policies": total_policies,
        "active_policies": active_policies,
        "inactive_policies": total_policies - active_policies,
        "severity_breakdown": severity_breakdown,
        "category_breakdown": category_breakdown,
        "rule_type_breakdown": rule_type_breakdown,
        "enforcement_breakdown": enforcement_breakdown
    }

