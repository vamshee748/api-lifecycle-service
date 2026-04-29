# API routes - Endpoints for managing APIs in the lifecycle platform
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db import get_db
from app.schemas import APICreate, APIUpdate, APIResponse, APIListResponse, APIStatusEnum
from app.services import create_api, get_api, get_apis, update_api, delete_api
from app.models import APIStatus

# Create router for API endpoints
router = APIRouter(
    prefix="/apis",
    tags=["APIs"],
    responses={
        404: {"description": "API not found"},
        500: {"description": "Internal server error"}
    }
)


@router.post(
    "",
    response_model=APIResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API",
    description="Create a new API record in the lifecycle management system",
    responses={
        201: {"description": "API successfully created"},
        400: {"description": "Invalid request data"},
        409: {"description": "API with same service_name and version already exists"},
        422: {"description": "Validation error"}
    }
)
def create_api_endpoint(
    api_data: APICreate,
    db: Session = Depends(get_db)
):
    """
    Create a new API with the provided information.
    
    **Request Body:**
    - **name**: Human-readable name of the API (required)
    - **service_name**: Internal service identifier (required)
    - **version**: Semantic version (e.g., v1.0.0 or 1.0.0) (required)
    - **status**: Lifecycle status (draft, published, deprecated, retired) (default: draft)
    - **description**: Detailed description of the API (optional)
    - **base_url**: Base URL for the API (optional)
    - **spec_url**: URL to the OpenAPI specification (optional)
    - **owner_team**: Team responsible for the API (optional)
    
    **Returns:**
    - Complete API record including generated ID and timestamps
    
    **Errors:**
    - 409: If an API with the same service_name and version already exists
    - 400: If request data violates database constraints
    - 422: If request data fails validation (e.g., invalid version format)
    """
    return create_api(db=db, api_data=api_data)


@router.get(
    "",
    response_model=APIListResponse,
    summary="List all APIs",
    description="Retrieve a paginated list of APIs with optional filtering",
    responses={
        200: {"description": "List of APIs successfully retrieved"}
    }
)
def list_apis_endpoint(
    skip: int = Query(0, ge=0, description="Number of records to skip for pagination"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records to return"),
    status_filter: Optional[APIStatusEnum] = Query(None, description="Filter by API status"),
    db: Session = Depends(get_db)
):
    """
    Retrieve a paginated list of APIs.
    
    **Query Parameters:**
    - **skip**: Number of records to skip (for pagination, default: 0)
    - **limit**: Maximum number of records to return (default: 100, max: 1000)
    - **status**: Filter by API status (optional)
    
    **Returns:**
    - Paginated list of APIs with total count and page information
    """
    # Convert enum to model enum if provided
    status_model_filter = None
    if status_filter:
        status_model_filter = APIStatus[status_filter.value.upper()]
    
    apis = get_apis(db=db, skip=skip, limit=limit, status_filter=status_model_filter)
    total = db.query(APIStatus).count() if not status_model_filter else \
            db.query(APIStatus).filter(APIStatus == status_model_filter).count()
    
    return {
        "total": total,
        "page": (skip // limit) + 1,
        "page_size": limit,
        "data": apis
    }


@router.get(
    "/{api_id}",
    response_model=APIResponse,
    summary="Get API by ID",
    description="Retrieve a specific API by its ID",
    responses={
        200: {"description": "API successfully retrieved"},
        404: {"description": "API not found"}
    }
)
def get_api_endpoint(
    api_id: int,
    db: Session = Depends(get_db)
):
    """
    Retrieve an API by its unique ID.
    
    **Path Parameters:**
    - **api_id**: Unique identifier of the API
    
    **Returns:**
    - Complete API record if found
    
    **Errors:**
    - 404: If API with the specified ID does not exist
    """
    db_api = get_api(db=db, api_id=api_id)
    
    if db_api is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API with ID {api_id} not found"
        )
    
    return db_api


@router.put(
    "/{api_id}",
    response_model=APIResponse,
    summary="Update an API",
    description="Update an existing API's information",
    responses={
        200: {"description": "API successfully updated"},
        404: {"description": "API not found"},
        400: {"description": "Invalid request data"}
    }
)
def update_api_endpoint(
    api_id: int,
    api_data: APIUpdate,
    db: Session = Depends(get_db)
):
    """
    Update an existing API record.
    
    **Path Parameters:**
    - **api_id**: Unique identifier of the API to update
    
    **Request Body:**
    - Any combination of API fields to update (all optional)
    
    **Returns:**
    - Updated API record
    
    **Errors:**
    - 404: If API with the specified ID does not exist
    - 400: If update violates database constraints
    """
    db_api = update_api(db=db, api_id=api_id, api_data=api_data)
    
    if db_api is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API with ID {api_id} not found"
        )
    
    return db_api


@router.delete(
    "/{api_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an API",
    description="Delete an API from the system",
    responses={
        204: {"description": "API successfully deleted"},
        404: {"description": "API not found"}
    }
)
def delete_api_endpoint(
    api_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete an API record.
    
    **Path Parameters:**
    - **api_id**: Unique identifier of the API to delete
    
    **Note:** This will cascade delete all associated versions and changes.
    
    **Errors:**
    - 404: If API with the specified ID does not exist
    """
    success = delete_api(db=db, api_id=api_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API with ID {api_id} not found"
        )
