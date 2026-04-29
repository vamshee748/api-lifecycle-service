# Business logic for API lifecycle management
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from fastapi import HTTPException, status
from typing import Optional, List
import logging

from app.models import API, APIStatus
from app.schemas import APICreate, APIUpdate, APIResponse

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
    Update an existing API record.
    
    Args:
        db: Database session
        api_id: API ID to update
        api_data: APIUpdate schema with fields to update
        
    Returns:
        Updated API model instance if found, None otherwise
        
    Raises:
        HTTPException: For database errors
    """
    try:
        db_api = get_api(db, api_id)
        
        if not db_api:
            return None
        
        # Update only provided fields
        update_data = api_data.model_dump(exclude_unset=True)
        
        for field, value in update_data.items():
            setattr(db_api, field, value)
        
        db.commit()
        db.refresh(db_api)
        
        logger.info(f"Successfully updated API ID: {api_id}")
        
        return db_api
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error updating API {api_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred"
        )


def delete_api(db: Session, api_id: int) -> bool:
    """
    Delete an API record.
    
    Args:
        db: Database session
        api_id: API ID to delete
        
    Returns:
        True if deleted, False if not found
        
    Raises:
        HTTPException: For database errors
    """
    try:
        db_api = get_api(db, api_id)
        
        if not db_api:
            return False
        
        db.delete(db_api)
        db.commit()
        
        logger.info(f"Successfully deleted API ID: {api_id}")
        
        return True
        
    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"Database error deleting API {api_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected database error occurred"
        )
