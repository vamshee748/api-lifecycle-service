# API Changes routes - Endpoints for tracking and managing API changes
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db import get_db
from app.schemas import APIChangeCreate, APIChangeUpdate, APIChangeResponse, APIChangeListResponse, ChangeTypeEnum
from app.services import (
    create_api_change,
    get_api_change,
    get_api_changes,
    get_changes_by_api,
    get_breaking_changes,
    update_api_change,
    delete_api_change
)
from app.models import ChangeType, APIChange

# Create router for API changes endpoints
router = APIRouter(
    prefix="/changes",
    tags=["Changes"],
    responses={
        404: {"description": "Change or API not found"},
        500: {"description": "Internal server error"}
    }
)


@router.post(
    "",
    response_model=APIChangeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log a new API change",
    description="Create a change tracking record for API modifications, version updates, or breaking changes",
    responses={
        201: {"description": "API change successfully logged"},
        400: {"description": "Invalid request data"},
        404: {"description": "Referenced API not found"},
        422: {"description": "Validation error"}
    }
)
def create_change_endpoint(
    change_data: APIChangeCreate,
    db: Session = Depends(get_db)
):
    """
    Log a new API change for tracking and governance.
    
    **Request Body:**
    - **api_id**: ID of the API being changed (required)
    - **from_version**: Source version (optional, null for initial version)
    - **to_version**: Target/current version (required)
    - **change_type**: Type of change - breaking, non_breaking, or addition (required)
    - **description**: Human-readable description of the change (required)
    - **details**: Detailed change information in JSON format (optional)
    
    **Change Types:**
    - **breaking**: Changes that break backward compatibility (e.g., removing fields, changing types)
    - **non_breaking**: Changes that maintain backward compatibility (e.g., bug fixes, optimizations)
    - **addition**: New features or endpoints that don't affect existing functionality
    
    **Returns:**
    - Complete change record including generated ID and timestamps
    
    **Errors:**
    - 404: If the referenced API does not exist
    - 400: If request data violates database constraints
    - 422: If request data fails validation
    
    **Example:**
    ```json
    {
      \"api_id\": 1,
      \"from_version\": \"v1.0.0\",
      \"to_version\": \"v1.1.0\",
      \"change_type\": \"breaking\",
      \"description\": \"Changed payment_method field from string to enum\",
      \"details\": \"{\\\"field\\\": \\\"payment_method\\\", \\\"old_type\\\": \\\"string\\\", \\\"new_type\\\": \\\"enum\\\"}\"
    }
    ```
    """
    return create_api_change(db=db, change_data=change_data)


@router.get(
    "",
    response_model=APIChangeListResponse,
    summary="List API changes",
    description="Retrieve a paginated list of API changes with optional filtering and metadata",
    responses={
        200: {"description": "List of API changes successfully retrieved with pagination metadata"}
    }
)
def list_changes_endpoint(
    api_id: Optional[int] = Query(None, description="Filter by specific API ID"),
    change_type: Optional[ChangeTypeEnum] = Query(None, description="Filter by change type"),
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    db: Session = Depends(get_db)
):
    """
    Retrieve a paginated list of API changes with optional filtering.
    
    **Query Parameters:**
    - **api_id**: Filter changes for a specific API (optional)
    - **change_type**: Filter by change type (breaking, non_breaking, addition) (optional)
    - **skip**: Number of records to skip (for pagination, default: 0)
    - **limit**: Maximum number of records to return (default: 100, max: 1000)
    
    **Returns:**
    - Paginated response with:
        - **total**: Total number of changes matching filters
        - **page**: Current page number
        - **page_size**: Number of items per page
        - **data**: List of change records ordered by most recent first
    
    **Use Cases:**
    - Get all changes across all APIs
    - Get changes for a specific API
    - Filter breaking changes for impact analysis
    - Track non-breaking updates
    
    **Examples:**
    ```
    GET /changes?limit=50                         # First 50 changes
    GET /changes?api_id=1                         # All changes for API 1
    GET /changes?change_type=breaking             # All breaking changes
    GET /changes?api_id=1&change_type=breaking    # Breaking changes for API 1
    GET /changes?skip=20&limit=10                 # Pagination: page 3 (skip 20, take 10)
    ```
    """
    # Convert enum to model enum if provided
    change_type_model = None
    if change_type:
        change_type_model = ChangeType[change_type.value.upper()]
    
    # Get changes with filters
    changes = get_api_changes(
        db=db,
        api_id=api_id,
        change_type=change_type_model,
        skip=skip,
        limit=limit
    )
    
    # Get total count with same filters
    query = db.query(APIChange)
    
    if api_id is not None:
        query = query.filter(APIChange.api_id == api_id)
    
    if change_type_model is not None:
        query = query.filter(APIChange.change_type == change_type_model)
    
    total = query.count()
    
    return {
        "total": total,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "page_size": limit,
        "data": changes
    }


@router.get(
    "/api/{api_id}",
    response_model=List[APIChangeResponse],
    summary="Get changes for a specific API",
    description="Retrieve all changes for a given API",
    responses={
        200: {"description": "List of API changes successfully retrieved"}
    }
)
def get_api_changes_endpoint(
    api_id: int = Path(..., description="ID of the API to get changes for"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    db: Session = Depends(get_db)
):
    """
    Get all changes for a specific API ordered by most recent first.
    
    **Path Parameters:**
    - **api_id**: Unique identifier of the API
    
    **Query Parameters:**
    - **skip**: Number of records to skip (default: 0)
    - **limit**: Maximum number of records to return (default: 100, max: 1000)
    
    **Returns:**
    - List of all changes for the specified API
    
    **Use Case:**
    - View complete change history for an API
    - Track evolution of a specific API over time
    """
    changes = get_changes_by_api(db=db, api_id=api_id, skip=skip, limit=limit)
    return changes


@router.get(
    "/breaking",
    response_model=List[APIChangeResponse],
    summary="Get breaking changes",
    description="Retrieve all breaking changes, optionally filtered by API",
    responses={
        200: {"description": "List of breaking changes successfully retrieved"}
    }
)
def get_breaking_changes_endpoint(
    api_id: Optional[int] = Query(None, description="Filter by specific API ID"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    db: Session = Depends(get_db)
):
    """
    Get all breaking changes across APIs or for a specific API.
    
    **Query Parameters:**
    - **api_id**: Filter breaking changes for a specific API (optional)
    - **skip**: Number of records to skip (default: 0)
    - **limit**: Maximum number of records to return (default: 100, max: 1000)
    
    **Returns:**
    - List of breaking changes ordered by most recent first
    
    **Use Cases:**
    - Impact analysis for downstream consumers
    - Notification systems for breaking changes
    - Compliance and governance reporting
    - Migration planning
    """
    changes = get_breaking_changes(db=db, api_id=api_id, skip=skip, limit=limit)
    return changes


@router.get(
    "/{change_id}",
    response_model=APIChangeResponse,
    summary="Get change by ID",
    description="Retrieve a specific API change by its ID",
    responses={
        200: {"description": "API change successfully retrieved"},
        404: {"description": "API change not found"}
    }
)
def get_change_endpoint(
    change_id: int = Path(..., description="ID of the change to retrieve"),
    db: Session = Depends(get_db)
):
    """
    Retrieve a specific API change by its unique ID.
    
    **Path Parameters:**
    - **change_id**: Unique identifier of the change
    
    **Returns:**
    - Complete change record if found
    
    **Errors:**
    - 404: If change with the specified ID does not exist
    """
    db_change = get_api_change(db=db, change_id=change_id)
    
    if db_change is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f\"API change with ID {change_id} not found\"
        )
    
    return db_change


@router.put(
    "/{change_id}",
    response_model=APIChangeResponse,
    summary="Update an API change",
    description="Update an existing API change record",
    responses={
        200: {"description": "API change successfully updated"},
        404: {"description": "API change not found"},
        400: {"description": "Invalid request data"}
    }
)
def update_change_endpoint(
    change_id: int = Path(..., description="ID of the change to update"),
    change_data: APIChangeUpdate = ...,
    db: Session = Depends(get_db)
):
    """
    Update an existing API change record.
    
    **Path Parameters:**
    - **change_id**: Unique identifier of the change to update
    
    **Request Body (all fields optional):**
    - **from_version**: Source version
    - **to_version**: Target version
    - **change_type**: Type of change
    - **description**: Change description
    - **details**: Detailed change information
    
    **Returns:**
    - Updated change record
    
    **Errors:**
    - 404: If change with the specified ID does not exist
    - 400: If update violates database constraints
    """
    db_change = update_api_change(db=db, change_id=change_id, change_data=change_data)
    
    if db_change is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f\"API change with ID {change_id} not found\"
        )
    
    return db_change


@router.delete(
    "/{change_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an API change",
    description="Delete an API change record from the system",
    responses={
        204: {"description": "API change successfully deleted"},
        404: {"description": "API change not found"}
    }
)
def delete_change_endpoint(
    change_id: int = Path(..., description="ID of the change to delete"),
    db: Session = Depends(get_db)
):
    """
    Delete an API change record.
    
    **Path Parameters:**
    - **change_id**: Unique identifier of the change to delete
    
    **Returns:**
    - 204 No Content (empty response body on success)
    
    **Errors:**
    - 404: If change with the specified ID does not exist
    
    **Note:** This permanently deletes the change record from the system.
    """
    success = delete_api_change(db=db, change_id=change_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f\"API change with ID {change_id} not found\"
        )
