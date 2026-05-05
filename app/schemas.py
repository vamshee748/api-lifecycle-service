# Pydantic schemas for request/response validation
from pydantic import BaseModel, Field, HttpUrl, validator, ConfigDict
from typing import Optional, List
from datetime import datetime
from enum import Enum


# Enums matching the database models
class APIStatusEnum(str, Enum):
    """API lifecycle status enumeration"""
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class ChangeTypeEnum(str, Enum):
    """Type of API change enumeration"""
    BREAKING = "breaking"
    NON_BREAKING = "non_breaking"
    ADDITION = "addition"


class SeverityEnum(str, Enum):
    """Policy severity level enumeration"""
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class EnforcementLevelEnum(str, Enum):
    """Policy enforcement level enumeration"""
    BLOCKING = "blocking"
    ADVISORY = "advisory"
    MONITORING = "monitoring"


# ============================================================
# Base Schemas
# ============================================================

class TimestampMixin(BaseModel):
    """Mixin for timestamp fields"""
    created_at: datetime = Field(..., description="Timestamp when the record was created")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the record was last updated")

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# API Schemas
# ============================================================

class APIBase(BaseModel):
    """Base schema for API with common fields"""
    name: str = Field(..., min_length=1, max_length=255, description="API name", examples=["Payment API"])
    service_name: str = Field(..., min_length=1, max_length=255, description="Service name", examples=["payment-service"])
    version: str = Field(..., min_length=1, max_length=50, description="API version", examples=["v1.0.0", "1.0.0"])
    status: APIStatusEnum = Field(default=APIStatusEnum.DRAFT, description="API lifecycle status")
    description: Optional[str] = Field(None, description="Detailed description of the API")
    base_url: Optional[str] = Field(None, max_length=500, description="Base URL for the API", examples=["https://api.example.com/v1"])
    spec_url: Optional[str] = Field(None, max_length=500, description="URL to the OpenAPI specification", examples=["https://api.example.com/openapi.json"])
    owner_team: Optional[str] = Field(None, max_length=255, description="Team responsible for the API", examples=["payments-team"])

    @validator('version')
    def validate_version_format(cls, v):
        """Validate version follows semantic versioning pattern"""
        import re
        # Support both vX.Y.Z and X.Y.Z formats
        pattern = r'^v?\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?$'
        if not re.match(pattern, v):
            raise ValueError('Version must follow semantic versioning format (e.g., 1.0.0 or v1.0.0)')
        return v

    @validator('base_url', 'spec_url')
    def validate_url_format(cls, v):
        """Validate URL format if provided"""
        if v is not None and v.strip():
            if not v.startswith(('http://', 'https://')):
                raise ValueError('URL must start with http:// or https://')
        return v

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "name": "Payment API",
                "service_name": "payment-service",
                "version": "v1.0.0",
                "status": "published",
                "description": "API for processing payments and managing transactions",
                "base_url": "https://api.example.com/payment/v1",
                "spec_url": "https://api.example.com/payment/v1/openapi.json",
                "owner_team": "payments-team"
            }
        }
    )


class APICreate(APIBase):
    """Schema for creating a new API"""
    pass


class APIUpdate(BaseModel):
    """Schema for updating an existing API (all fields optional)"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="API name")
    service_name: Optional[str] = Field(None, min_length=1, max_length=255, description="Service name")
    version: Optional[str] = Field(None, min_length=1, max_length=50, description="API version")
    status: Optional[APIStatusEnum] = Field(None, description="API lifecycle status")
    description: Optional[str] = Field(None, description="Detailed description of the API")
    base_url: Optional[str] = Field(None, max_length=500, description="Base URL for the API")
    spec_url: Optional[str] = Field(None, max_length=500, description="URL to the OpenAPI specification")
    owner_team: Optional[str] = Field(None, max_length=255, description="Team responsible for the API")

    @validator('version')
    def validate_version_format(cls, v):
        """Validate version follows semantic versioning pattern"""
        if v is not None:
            import re
            pattern = r'^v?\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?$'
            if not re.match(pattern, v):
                raise ValueError('Version must follow semantic versioning format (e.g., 1.0.0 or v1.0.0)')
        return v

    model_config = ConfigDict(from_attributes=True)


class APIResponse(APIBase, TimestampMixin):
    """Schema for API response with all fields"""
    id: int = Field(..., description="Unique identifier for the API")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "Payment API",
                "service_name": "payment-service",
                "version": "v1.0.0",
                "status": "published",
                "description": "API for processing payments and managing transactions",
                "base_url": "https://api.example.com/payment/v1",
                "spec_url": "https://api.example.com/payment/v1/openapi.json",
                "owner_team": "payments-team",
                "created_at": "2026-04-20T10:30:00Z",
                "updated_at": "2026-04-23T14:20:00Z"
            }
        }
    )


class APIListResponse(BaseModel):
    """Schema for paginated API list response"""
    total: int = Field(..., description="Total number of APIs")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Number of items per page")
    data: List[APIResponse] = Field(..., description="List of APIs")

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# API Version Schemas
# ============================================================

class APIVersionBase(BaseModel):
    """Base schema for API version"""
    version: str = Field(..., min_length=1, max_length=50, description="Version identifier", examples=["v1.0.0"])
    spec_content: Optional[str] = Field(None, description="OpenAPI specification content (JSON or YAML)")
    is_active: bool = Field(default=True, description="Whether this version is currently active")

    @validator('version')
    def validate_version_format(cls, v):
        """Validate version follows semantic versioning pattern"""
        import re
        pattern = r'^v?\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?$'
        if not re.match(pattern, v):
            raise ValueError('Version must follow semantic versioning format (e.g., 1.0.0 or v1.0.0)')
        return v

    model_config = ConfigDict(from_attributes=True)


class APIVersionCreate(APIVersionBase):
    """Schema for creating a new API version"""
    api_id: int = Field(..., gt=0, description="ID of the parent API")


class APIVersionUpdate(BaseModel):
    """Schema for updating an API version"""
    version: Optional[str] = Field(None, min_length=1, max_length=50, description="Version identifier")
    spec_content: Optional[str] = Field(None, description="OpenAPI specification content")
    is_active: Optional[bool] = Field(None, description="Whether this version is currently active")

    model_config = ConfigDict(from_attributes=True)


class APIVersionResponse(APIVersionBase, TimestampMixin):
    """Schema for API version response"""
    id: int = Field(..., description="Unique identifier for the version")
    api_id: int = Field(..., description="ID of the parent API")

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# API Change Schemas
# ============================================================

class APIChangeBase(BaseModel):
    """Base schema for API change"""
    from_version: Optional[str] = Field(None, max_length=50, description="Source version", examples=["v1.0.0"])
    to_version: str = Field(..., max_length=50, description="Target version", examples=["v1.1.0"])
    change_type: ChangeTypeEnum = Field(..., description="Type of change")
    description: str = Field(..., min_length=1, description="Human-readable description of the change")
    details: Optional[str] = Field(None, description="Detailed change information (JSON format)")

    model_config = ConfigDict(from_attributes=True)


class APIChangeCreate(APIChangeBase):
    """Schema for creating a new API change"""
    api_id: int = Field(..., gt=0, description="ID of the API")


class APIChangeUpdate(BaseModel):
    """Schema for updating an API change"""
    from_version: Optional[str] = Field(None, max_length=50, description="Source version")
    to_version: Optional[str] = Field(None, max_length=50, description="Target version")
    change_type: Optional[ChangeTypeEnum] = Field(None, description="Type of change")
    description: Optional[str] = Field(None, min_length=1, description="Human-readable description")
    details: Optional[str] = Field(None, description="Detailed change information (JSON format)")

    model_config = ConfigDict(from_attributes=True)


class APIChangeResponse(APIChangeBase, TimestampMixin):
    """Schema for API change response"""
    id: int = Field(..., description="Unique identifier for the change")
    api_id: int = Field(..., description="ID of the API")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "api_id": 1,
                "from_version": "v1.0.0",
                "to_version": "v1.1.0",
                "change_type": "breaking",
                "description": "Changed payment method field from string to enum",
                "details": "{\"field\": \"payment_method\", \"old_type\": \"string\", \"new_type\": \"enum\"}",
                "created_at": "2026-04-23T10:30:00Z",
                "updated_at": None
            }
        }
    )


class APIChangeListResponse(BaseModel):
    """Schema for paginated API change list response"""
    total: int = Field(..., description="Total number of changes")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=1000, description="Number of items per page")
    data: List[APIChangeResponse] = Field(..., description="List of API changes")

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Governance Policy Schemas
# ============================================================

class GovernancePolicyBase(BaseModel):
    """Base schema for governance policy"""
    name: str = Field(..., min_length=1, max_length=255, description="Policy name", examples=["Breaking Change Approval"])
    description: Optional[str] = Field(None, description="Detailed description of the policy")
    rule_type: str = Field(..., max_length=100, description="Type of rule", examples=["approval_required", "naming_convention", "versioning_standard"])
    rule_config: Optional[str] = Field(None, description="Rule configuration in JSON format")
    is_active: bool = Field(default=True, description="Whether this policy is currently active")
    severity: SeverityEnum = Field(default=SeverityEnum.WARNING, description="Severity level of policy violations")
    category: Optional[str] = Field(None, max_length=100, description="Policy category", examples=["security", "compliance", "standards"])
    owner_team: Optional[str] = Field(None, max_length=255, description="Team responsible for this policy", examples=["architecture-team", "security-team"])
    enforcement_level: str = Field(default="advisory", max_length=50, description="Enforcement level", examples=["blocking", "advisory", "monitoring"])

    @validator('rule_type')
    def validate_rule_type(cls, v):
        """Validate rule type format"""
        if v and not v.replace('_', '').isalnum():
            raise ValueError('Rule type must contain only alphanumeric characters and underscores')
        return v

    @validator('enforcement_level')
    def validate_enforcement_level(cls, v):
        """Validate enforcement level"""
        valid_levels = {'blocking', 'advisory', 'monitoring'}
        if v.lower() not in valid_levels:
            raise ValueError(f'Enforcement level must be one of: {", ".join(valid_levels)}')
        return v.lower()

    @validator('rule_config')
    def validate_rule_config(cls, v):
        """Validate rule_config is valid JSON if provided"""
        if v is not None and v.strip():
            import json
            try:
                json.loads(v)
            except json.JSONDecodeError:
                raise ValueError('rule_config must be valid JSON')
        return v

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "name": "Breaking Change Approval",
                "description": "All breaking changes require approval from architecture team",
                "rule_type": "approval_required",
                "rule_config": "{\"approvers\": [\"architecture-team\"], \"min_approvals\": 2}",
                "is_active": True,
                "severity": "critical",
                "category": "compliance",
                "owner_team": "architecture-team",
                "enforcement_level": "blocking"
            }
        }
    )


class GovernancePolicyCreate(GovernancePolicyBase):
    """Schema for creating a new governance policy"""
    pass


class GovernancePolicyUpdate(BaseModel):
    """Schema for updating a governance policy"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Policy name")
    description: Optional[str] = Field(None, description="Detailed description of the policy")
    rule_type: Optional[str] = Field(None, max_length=100, description="Type of rule")
    rule_config: Optional[str] = Field(None, description="Rule configuration in JSON format")
    is_active: Optional[bool] = Field(None, description="Whether this policy is currently active")
    severity: Optional[SeverityEnum] = Field(None, description="Severity level of policy violations")
    category: Optional[str] = Field(None, max_length=100, description="Policy category")
    owner_team: Optional[str] = Field(None, max_length=255, description="Team responsible for this policy")
    enforcement_level: Optional[str] = Field(None, max_length=50, description="Enforcement level")

    @validator('rule_type')
    def validate_rule_type(cls, v):
        """Validate rule type format"""
        if v and not v.replace('_', '').isalnum():
            raise ValueError('Rule type must contain only alphanumeric characters and underscores')
        return v

    @validator('enforcement_level')
    def validate_enforcement_level(cls, v):
        """Validate enforcement level"""
        if v is not None:
            valid_levels = {'blocking', 'advisory', 'monitoring'}
            if v.lower() not in valid_levels:
                raise ValueError(f'Enforcement level must be one of: {", ".join(valid_levels)}')
            return v.lower()
        return v

    @validator('rule_config')
    def validate_rule_config(cls, v):
        """Validate rule_config is valid JSON if provided"""
        if v is not None and v.strip():
            import json
            try:
                json.loads(v)
            except json.JSONDecodeError:
                raise ValueError('rule_config must be valid JSON')
        return v

    model_config = ConfigDict(from_attributes=True)


class GovernancePolicyResponse(GovernancePolicyBase, TimestampMixin):
    """Schema for governance policy response"""
    id: int = Field(..., description="Unique identifier for the policy")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 1,
                "name": "Breaking Change Approval",
                "description": "All breaking changes require approval from architecture team",
                "rule_type": "approval_required",
                "rule_config": "{\"approvers\": [\"architecture-team\"], \"min_approvals\": 2}",
                "is_active": True,
                "severity": "critical",
                "category": "compliance",
                "owner_team": "architecture-team",
                "enforcement_level": "blocking",
                "created_at": "2026-04-20T10:30:00Z",
                "updated_at": None
            }
        }
    )


class GovernancePolicyListResponse(BaseModel):
    """Schema for paginated governance policy list response"""
    total: int = Field(..., description="Total number of policies")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=1000, description="Number of items per page")
    data: List[GovernancePolicyResponse] = Field(..., description="List of governance policies")

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Generic Response Schemas
# ============================================================

class MessageResponse(BaseModel):
    """Generic message response schema"""
    message: str = Field(..., description="Response message")
    detail: Optional[str] = Field(None, description="Additional details")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "message": "Operation completed successfully",
                "detail": "API was created with ID 123"
            }
        }
    )


class ErrorResponse(BaseModel):
    """Error response schema"""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Additional error details")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Error timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "ValidationError",
                "message": "Invalid input data",
                "detail": "Version must follow semantic versioning format",
                "timestamp": "2026-04-23T14:30:00Z"
            }
        }
    )
