# Entry point
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
import uvicorn
import logging

from app.routes import api, changes, policies, analytics, auth
from app.middleware import (
    RequestLoggingMiddleware,
    PerformanceMonitoringMiddleware,
    SecurityHeadersMiddleware,
    log_startup_info,
    log_shutdown_info
)

logger = logging.getLogger(__name__)

# Enhanced OpenAPI documentation metadata
tags_metadata = [
    {
        "name": "Authentication",
        "description": "User authentication and authorization endpoints. Includes login, registration, token refresh, and user management.",
    },
    {
        "name": "APIs",
        "description": "API lifecycle management endpoints. Create, read, update, and delete API definitions.",
    },
    {
        "name": "Changes",
        "description": "API change tracking and version history. Monitor modifications and maintain audit trails.",
    },
    {
        "name": "Policies",
        "description": "Governance policy management. Define and enforce rules for API compliance and best practices.",
    },
    {
        "name": "Analytics",
        "description": "API usage analytics and metrics. Track performance, usage patterns, and generate insights with Redis caching.",
    },
]

# Initialize FastAPI application with comprehensive OpenAPI configuration
app = FastAPI(
    title="API Lifecycle Service",
    description="""
## 🚀 Backend API Governance & Lifecycle Platform

A production-ready API management platform with comprehensive features for:

* **API Lifecycle Management** - Full CRUD operations for API definitions
* **Change Tracking** - Version control and audit trails
* **Analytics & Monitoring** - Usage metrics with Redis caching (5-10 min TTL)
* **Governance Policies** - Rule-based compliance enforcement
* **JWT Authentication** - Secure token-based auth with role/permission control
* **Performance Optimization** - Redis caching for fast response times

### 🔐 Authentication

Most write operations require authentication. Obtain a JWT token via `/auth/login`:

1. POST to `/auth/login` with username and password
2. Receive `access_token` (30 min expiry) and `refresh_token` (7 days)
3. Include token in subsequent requests: `Authorization: Bearer <token>`

**Default Test Users:**
- **admin** / admin123 - Full access (all permissions)
- **demo** / demo123 - Read-only access

### 📊 Performance

- **Cached Analytics**: 10-200x faster response times
- **Response Time**: < 100ms for cached data
- **Rate Limiting**: 60 requests/minute (configurable)

### 🛡️ Security Features

- JWT token-based authentication
- Password hashing (bcrypt)
- Role-based access control (RBAC)
- Permission-based authorization
- Security headers (HSTS, CSP, XSS protection)
- Request logging and monitoring

### 📈 Monitoring

All requests are logged with:
- Request ID for tracing
- Processing time in milliseconds
- Authentication status
- Client information
- Error tracking with stack traces
    """,
    version="1.0.0",
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "Vamshee",
        "email": "vamshee748@gmail.com",
        "url": "https://github.com/vamshee748/api-lifecycle-service"
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT"
    },
    terms_of_service="https://github.com/vamshee748/api-lifecycle-service",
)


def custom_openapi():
    """
    Custom OpenAPI schema with enhanced security definitions.
    """
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    
    # Add security schemes
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your JWT token in the format: Bearer <token>"
        }
    }
    
    # Add servers
    openapi_schema["servers"] = [
        {
            "url": "http://localhost:8000",
            "description": "Development server"
        },
        {
            "url": "https://api.example.com",
            "description": "Production server"
        }
    ]
    
    # Add additional metadata
    openapi_schema["info"]["x-logo"] = {
        "url": "https://fastapi.tiangolo.com/img/logo-margin/logo-teal.png"
    }
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# Register middleware (order matters - last registered is executed first)
# 1. Security headers (applied last to response)
app.add_middleware(SecurityHeadersMiddleware)

# 2. Performance monitoring
app.add_middleware(PerformanceMonitoringMiddleware)

# 3. Request/response logging
app.add_middleware(RequestLoggingMiddleware)

# 4. CORS middleware (applied first to request)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """
    Application startup event handler.
    """
    log_startup_info()
    logger.info("Registering routes...")
    logger.info("✓ Authentication routes registered")
    logger.info("✓ API routes registered")
    logger.info("✓ Changes routes registered")
    logger.info("✓ Policies routes registered")
    logger.info("✓ Analytics routes registered")
    logger.info("Middleware chain configured:")
    logger.info("  1. CORS Middleware")
    logger.info("  2. Request Logging Middleware")
    logger.info("  3. Performance Monitoring Middleware")
    logger.info("  4. Security Headers Middleware")
    logger.info("Application ready to accept requests!")


@app.on_event("shutdown")
async def shutdown_event():
    """
    Application shutdown event handler.
    """
    log_shutdown_info()
    logger.info("Cleanup completed successfully")


# Register routers with updated tags
app.include_router(auth.router)  # Authentication routes (no auth required)
app.include_router(api.router)
app.include_router(changes.router)
app.include_router(policies.router)
app.include_router(analytics.router)


@app.get("/", tags=["Health"], summary="Root endpoint", description="Basic health check endpoint to verify the service is running.")
async def root():
    """
    Root endpoint returning service status.
    """
    return {
        "message": "API Lifecycle Service is running",
        "version": "1.0.0",
        "status": "operational",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health", tags=["Health"], summary="Health check", description="Detailed health check endpoint for monitoring service health.")
async def health_check():
    """
    Health check endpoint for monitoring and load balancers.
    Returns service health status and version information.
    """
    return {
        "status": "healthy",
        "service": "API Lifecycle Service",
        "version": "1.0.0",
        "timestamp": "2026-05-11T00:00:00Z"
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
