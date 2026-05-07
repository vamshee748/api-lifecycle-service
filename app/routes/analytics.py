# Analytics routes - Endpoints for API usage analytics and metrics
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timedelta

from app.db import get_db
from app.schemas import (
    AnalyticsCreate,
    AnalyticsUpdate,
    AnalyticsResponse,
    AnalyticsSummary,
    EndpointAnalytics,
    ConsumerAnalytics,
    AnalyticsTimeSeriesResponse,
    TimeSeriesDataPoint,
    AnalyticsListResponse
)
from app.services import (
    create_analytics_record,
    get_analytics_record,
    get_analytics_records,
    get_analytics_summary,
    get_endpoint_analytics,
    get_consumer_analytics,
    get_time_series_analytics,
    get_top_apis_by_usage
)
from app.models import APIUsageAnalytics

# Create router for analytics endpoints
router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
    responses={
        404: {"description": "Analytics record or API not found"},
        500: {"description": "Internal server error"}
    }
)


@router.post(
    "",
    response_model=AnalyticsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create analytics record",
    description="Create a new analytics record for API usage tracking",
    responses={
        201: {"description": "Analytics record successfully created"},
        400: {"description": "Invalid request data"},
        404: {"description": "Referenced API not found"},
        422: {"description": "Validation error"}
    }
)
def create_analytics_endpoint(
    analytics_data: AnalyticsCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new analytics record for tracking API usage metrics.
    
    **Request Body:**
    - **api_id**: ID of the API being tracked (required)
    - **endpoint**: Specific endpoint path (optional)
    - **http_method**: HTTP method (GET, POST, etc.) (optional)
    - **request_count**: Total number of requests (default: 0)
    - **success_count**: Number of successful requests (default: 0)
    - **error_count**: Number of failed requests (default: 0)
    - **avg_response_time_ms**: Average response time in milliseconds (optional)
    - **tracked_date**: Date for metrics tracking (required)
    - **consumer_id**: ID of the API consumer (optional)
    - **environment**: Environment (production, staging, etc.) (optional)
    - **status_2xx_count**: Count of 2xx responses (default: 0)
    - **status_4xx_count**: Count of 4xx responses (default: 0)
    - **status_5xx_count**: Count of 5xx responses (default: 0)
    
    **Returns:**
    - Complete analytics record with computed metrics (error_rate, success_rate)
    
    **Errors:**
    - 404: If the referenced API does not exist
    - 400: If duplicate analytics record exists
    - 422: If request data fails validation
    """
    return create_analytics_record(db=db, analytics_data=analytics_data)


@router.get(
    "",
    response_model=AnalyticsListResponse,
    summary="List analytics records",
    description="Retrieve analytics records with filtering and pagination",
    responses={
        200: {"description": "Analytics records successfully retrieved"}
    }
)
def list_analytics_endpoint(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
    api_id: Optional[int] = Query(None, description="Filter by API ID"),
    endpoint: Optional[str] = Query(None, description="Filter by endpoint"),
    environment: Optional[str] = Query(None, description="Filter by environment"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    db: Session = Depends(get_db)
):
    """
    Retrieve a list of analytics records with comprehensive filtering.
    
    **Query Parameters:**
    - **skip**: Number of records to skip (pagination, default: 0)
    - **limit**: Maximum records to return (default: 100, max: 1000)
    - **api_id**: Filter by specific API
    - **endpoint**: Filter by specific endpoint path
    - **environment**: Filter by environment (production, staging, etc.)
    - **start_date**: Filter records from this date onwards
    - **end_date**: Filter records up to this date
    
    **Returns:**
    - Paginated list of analytics records with metadata
    
    **Example:**
    ```
    GET /analytics?api_id=1&environment=production&start_date=2026-05-01
    ```
    """
    records = get_analytics_records(
        db=db,
        skip=skip,
        limit=limit,
        api_id=api_id,
        endpoint=endpoint,
        environment=environment,
        start_date=start_date,
        end_date=end_date
    )
    
    # Get total count
    total_query = db.query(APIUsageAnalytics)
    if api_id:
        total_query = total_query.filter(APIUsageAnalytics.api_id == api_id)
    if endpoint:
        total_query = total_query.filter(APIUsageAnalytics.endpoint == endpoint)
    if environment:
        total_query = total_query.filter(APIUsageAnalytics.environment == environment)
    if start_date:
        total_query = total_query.filter(APIUsageAnalytics.tracked_date >= start_date)
    if end_date:
        total_query = total_query.filter(APIUsageAnalytics.tracked_date <= end_date)
    
    total = total_query.count()
    
    return {
        "total": total,
        "page": (skip // limit) + 1 if limit > 0 else 1,
        "page_size": limit,
        "data": records
    }


@router.get(
    "/summary",
    response_model=AnalyticsSummary,
    summary="Get analytics summary",
    description="Get aggregated analytics summary with overall metrics",
    responses={
        200: {"description": "Analytics summary successfully retrieved"}
    }
)
def get_analytics_summary_endpoint(
    api_id: Optional[int] = Query(None, description="Filter by API ID"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    environment: Optional[str] = Query(None, description="Filter by environment"),
    db: Session = Depends(get_db)
):
    """
    Get aggregated analytics summary with overall metrics.
    
    **Query Parameters:**
    - **api_id**: Optional API ID to filter results
    - **start_date**: Start date for analysis period
    - **end_date**: End date for analysis period
    - **environment**: Filter by environment
    
    **Returns:**
    - Aggregated summary including:
      - Total requests, successes, and errors
      - Average response time
      - Overall error and success rates
      - Number of unique consumers and endpoints
      - Date range of the analysis
    
    **Example:**
    ```
    GET /analytics/summary?api_id=1&start_date=2026-05-01&end_date=2026-05-07
    ```
    
    **Use Cases:**
    - Dashboard overview
    - Performance monitoring
    - Health check reporting
    - SLA compliance tracking
    """
    return get_analytics_summary(
        db=db,
        api_id=api_id,
        start_date=start_date,
        end_date=end_date,
        environment=environment
    )


@router.get(
    "/endpoints",
    response_model=List[EndpointAnalytics],
    summary="Get per-endpoint analytics",
    description="Get analytics aggregated by endpoint",
    responses={
        200: {"description": "Endpoint analytics successfully retrieved"}
    }
)
def get_endpoint_analytics_endpoint(
    api_id: Optional[int] = Query(None, description="Filter by API ID"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    environment: Optional[str] = Query(None, description="Filter by environment"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum endpoints to return"),
    db: Session = Depends(get_db)
):
    """
    Get analytics data aggregated by endpoint.
    
    **Query Parameters:**
    - **api_id**: Optional API ID to filter results
    - **start_date**: Start date for analysis period
    - **end_date**: End date for analysis period
    - **environment**: Filter by environment
    - **limit**: Maximum number of endpoints to return (default: 100)
    
    **Returns:**
    - List of endpoint analytics with:
      - Endpoint path and HTTP method
      - Request counts (total, success, error)
      - Average response time
      - Error rate
    
    **Ordered by:** Request count (descending)
    
    **Use Cases:**
    - Identify most-used endpoints
    - Find problematic endpoints with high error rates
    - Optimize slow endpoints
    - Capacity planning
    """
    return get_endpoint_analytics(
        db=db,
        api_id=api_id,
        start_date=start_date,
        end_date=end_date,
        environment=environment,
        limit=limit
    )


@router.get(
    "/consumers",
    response_model=List[ConsumerAnalytics],
    summary="Get per-consumer analytics",
    description="Get analytics aggregated by consumer/client",
    responses={
        200: {"description": "Consumer analytics successfully retrieved"}
    }
)
def get_consumer_analytics_endpoint(
    api_id: Optional[int] = Query(None, description="Filter by API ID"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    environment: Optional[str] = Query(None, description="Filter by environment"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum consumers to return"),
    db: Session = Depends(get_db)
):
    """
    Get analytics data aggregated by consumer/client.
    
    **Query Parameters:**
    - **api_id**: Optional API ID to filter results
    - **start_date**: Start date for analysis period
    - **end_date**: End date for analysis period
    - **environment**: Filter by environment
    - **limit**: Maximum number of consumers to return (default: 100)
    
    **Returns:**
    - List of consumer analytics with:
      - Consumer ID and name
      - Request count
      - Error count and rate
    
    **Ordered by:** Request count (descending)
    
    **Use Cases:**
    - Identify top API consumers
    - Monitor consumer-specific error rates
    - Usage-based billing
    - Rate limiting decisions
    - Customer support and account management
    """
    return get_consumer_analytics(
        db=db,
        api_id=api_id,
        start_date=start_date,
        end_date=end_date,
        environment=environment,
        limit=limit
    )


@router.get(
    "/timeseries",
    response_model=AnalyticsTimeSeriesResponse,
    summary="Get time series analytics",
    description="Get analytics data as a time series",
    responses={
        200: {"description": "Time series analytics successfully retrieved"}
    }
)
def get_time_series_analytics_endpoint(
    api_id: Optional[int] = Query(None, description="Filter by API ID"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    environment: Optional[str] = Query(None, description="Filter by environment"),
    granularity: str = Query("day", description="Time granularity (hour, day, week, month)"),
    db: Session = Depends(get_db)
):
    """
    Get analytics data as a time series for trend analysis.
    
    **Query Parameters:**
    - **api_id**: Optional API ID to filter results
    - **start_date**: Start date for analysis period
    - **end_date**: End date for analysis period
    - **environment**: Filter by environment
    - **granularity**: Time granularity (hour, day, week, month)
    
    **Returns:**
    - Time series data with:
      - Timestamp for each data point
      - Request count
      - Error count
      - Average response time
    
    **Ordered by:** Timestamp (ascending)
    
    **Use Cases:**
    - Trend analysis and forecasting
    - Identify traffic patterns
    - Detect anomalies
    - Capacity planning
    - Performance monitoring over time
    - Generate charts and graphs
    """
    data_points = get_time_series_analytics(
        db=db,
        api_id=api_id,
        start_date=start_date,
        end_date=end_date,
        environment=environment,
        granularity=granularity
    )
    
    return {
        "api_id": api_id,
        "data_points": data_points,
        "total_data_points": len(data_points)
    }


@router.get(
    "/top-apis",
    summary="Get top APIs by usage",
    description="Get top APIs ranked by request volume",
    responses={
        200: {"description": "Top APIs successfully retrieved"}
    }
)
def get_top_apis_endpoint(
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    environment: Optional[str] = Query(None, description="Filter by environment"),
    limit: int = Query(10, ge=1, le=100, description="Number of top APIs to return"),
    db: Session = Depends(get_db)
):
    """
    Get top APIs ranked by usage/request volume.
    
    **Query Parameters:**
    - **start_date**: Start date for analysis period
    - **end_date**: End date for analysis period
    - **environment**: Filter by environment
    - **limit**: Number of top APIs to return (default: 10, max: 100)
    
    **Returns:**
    - List of top APIs with:
      - API details (ID, name, service name, version)
      - Total requests
      - Total errors
      - Error rate
    
    **Ordered by:** Total requests (descending)
    
    **Use Cases:**
    - Identify most popular APIs
    - Resource allocation and scaling decisions
    - Prioritize optimization efforts
    - Marketing and business insights
    - API portfolio management
    """
    return get_top_apis_by_usage(
        db=db,
        start_date=start_date,
        end_date=end_date,
        environment=environment,
        limit=limit
    )


@router.get(
    "/{analytics_id}",
    response_model=AnalyticsResponse,
    summary="Get specific analytics record",
    description="Retrieve a specific analytics record by ID",
    responses={
        200: {"description": "Analytics record successfully retrieved"},
        404: {"description": "Analytics record not found"}
    }
)
def get_analytics_endpoint(
    analytics_id: int = Path(..., gt=0, description="ID of the analytics record"),
    db: Session = Depends(get_db)
):
    """
    Retrieve a specific analytics record by ID.
    
    **Path Parameters:**
    - **analytics_id**: Unique identifier of the analytics record
    
    **Returns:**
    - Complete analytics record with all metrics
    
    **Errors:**
    - 404: If analytics record with specified ID does not exist
    """
    db_analytics = get_analytics_record(db=db, analytics_id=analytics_id)
    
    if db_analytics is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analytics record with ID {analytics_id} not found"
        )
    
    return db_analytics
