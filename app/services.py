# Business logic for API lifecycle management
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from fastapi import HTTPException, status
from typing import Optional, List
import logging

from app.models import API, APIStatus, APIChange, ChangeType
from app.schemas import APICreate, APIUpdate, APIResponse, APIChangeCreate, APIChangeUpdate

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
