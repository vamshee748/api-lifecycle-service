"""
Middleware components for the API Lifecycle Service.
Includes request/response logging, error handling, and performance monitoring.
"""

import time
import logging
import json
from datetime import datetime
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log', mode='a')
    ]
)

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for logging all HTTP requests and responses.
    Tracks request/response details, performance metrics, and errors.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate unique request ID
        request_id = f"{int(time.time() * 1000)}-{id(request)}"
        
        # Extract request details
        client_host = request.client.host if request.client else "unknown"
        method = request.method
        url = str(request.url)
        path = request.url.path
        
        # Extract headers
        user_agent = request.headers.get("user-agent", "unknown")
        authorization = request.headers.get("authorization", "")
        content_type = request.headers.get("content-type", "")
        
        # Determine if user is authenticated
        is_authenticated = bool(authorization and authorization.startswith("Bearer "))
        
        # Start timing
        start_time = time.time()
        
        # Log request
        logger.info(
            f"[{request_id}] REQUEST: {method} {path} | "
            f"Client: {client_host} | "
            f"Auth: {'Yes' if is_authenticated else 'No'} | "
            f"User-Agent: {user_agent}"
        )
        
        # Log request body for POST/PUT/PATCH (excluding sensitive routes)
        if method in ["POST", "PUT", "PATCH"] and "/auth/login" not in path and "/auth/register" not in path:
            try:
                body = await request.body()
                if body and len(body) < 10000:  # Limit body size to log
                    try:
                        body_json = json.loads(body)
                        logger.debug(f"[{request_id}] REQUEST BODY: {json.dumps(body_json)}")
                    except:
                        logger.debug(f"[{request_id}] REQUEST BODY: (non-JSON, {len(body)} bytes)")
                
                # Reset body for downstream processing
                async def receive() -> Message:
                    return {"type": "http.request", "body": body}
                
                request._receive = receive
            except Exception as e:
                logger.warning(f"[{request_id}] Could not read request body: {str(e)}")
        
        # Process request
        try:
            response = await call_next(request)
            
            # Calculate processing time
            process_time = time.time() - start_time
            process_time_ms = round(process_time * 1000, 2)
            
            # Extract response details
            status_code = response.status_code
            
            # Determine log level based on status code
            if status_code >= 500:
                log_level = logging.ERROR
            elif status_code >= 400:
                log_level = logging.WARNING
            else:
                log_level = logging.INFO
            
            # Log response
            logger.log(
                log_level,
                f"[{request_id}] RESPONSE: {method} {path} | "
                f"Status: {status_code} | "
                f"Time: {process_time_ms}ms | "
                f"Client: {client_host}"
            )
            
            # Add custom headers to response
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time_ms)
            
            return response
            
        except Exception as exc:
            # Calculate processing time even on error
            process_time = time.time() - start_time
            process_time_ms = round(process_time * 1000, 2)
            
            # Log exception
            logger.error(
                f"[{request_id}] EXCEPTION: {method} {path} | "
                f"Error: {str(exc)} | "
                f"Time: {process_time_ms}ms | "
                f"Client: {client_host}"
            )
            logger.error(f"[{request_id}] Traceback: {traceback.format_exc()}")
            
            # Return error response
            return JSONResponse(
                status_code=500,
                content={
                    "detail": "Internal server error",
                    "request_id": request_id,
                    "timestamp": datetime.utcnow().isoformat()
                },
                headers={
                    "X-Request-ID": request_id,
                    "X-Process-Time": str(process_time_ms)
                }
            )


class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """
    Middleware for monitoring API performance and logging slow requests.
    """
    
    SLOW_REQUEST_THRESHOLD_MS = 1000  # Log warning if request takes > 1 second
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        response = await call_next(request)
        
        process_time = time.time() - start_time
        process_time_ms = round(process_time * 1000, 2)
        
        # Log slow requests
        if process_time_ms > self.SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(
                f"SLOW REQUEST: {request.method} {request.url.path} | "
                f"Time: {process_time_ms}ms | "
                f"Threshold: {self.SLOW_REQUEST_THRESHOLD_MS}ms"
            )
        
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware for adding security headers to all responses.
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        
        return response


def log_startup_info():
    """
    Log application startup information.
    """
    logger.info("=" * 80)
    logger.info("API Lifecycle Service Starting")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    logger.info(f"Python Logging Level: {logging.getLevelName(logger.level)}")
    logger.info("=" * 80)


def log_shutdown_info():
    """
    Log application shutdown information.
    """
    logger.info("=" * 80)
    logger.info("API Lifecycle Service Shutting Down")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    logger.info("=" * 80)
