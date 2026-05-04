# DB models - Production-ready SQLAlchemy models for API lifecycle management
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum as SQLEnum, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base
import enum


# ============================================================
# Enums for API lifecycle states
# ============================================================

class APIStatus(str, enum.Enum):
    """Enumeration for API lifecycle status states"""
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class ChangeType(str, enum.Enum):
    """Enumeration for types of API changes"""
    BREAKING = "breaking"
    NON_BREAKING = "non_breaking"
    ADDITION = "addition"


# ============================================================
# Base model class with common fields
# ============================================================

class BaseModel:
    """
    Base model class providing common fields for all entities:
    - id: Primary key with index
    - created_at: Automatic timestamp on creation
    - updated_at: Automatic timestamp on update
    """
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, comment="Timestamp when the record was created")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True, comment="Timestamp when the record was last updated")


# ============================================================
# API Model - Core entity for managing APIs
# ============================================================

class API(Base, BaseModel):
    """
    API Model - Represents an API in the lifecycle management system
    
    Tracks API metadata, status, ownership, and provides relationships
    to versions and changes.
    """
    __tablename__ = "apis"
    
    # Core fields
    name = Column(String(255), nullable=False, index=True, comment="Human-readable name of the API")
    service_name = Column(String(255), nullable=False, index=True, comment="Internal service identifier")
    version = Column(String(50), nullable=False, comment="Current version of the API")
    status = Column(SQLEnum(APIStatus), default=APIStatus.DRAFT, nullable=False, index=True, comment="Current lifecycle status")
    description = Column(Text, nullable=True, comment="Detailed description of the API")
    base_url = Column(String(500), nullable=True, comment="Base URL for the API")
    spec_url = Column(String(500), nullable=True, comment="URL to the OpenAPI specification")
    owner_team = Column(String(255), nullable=True, index=True, comment="Team responsible for the API")
    
    # Relationships
    versions = relationship("APIVersion", back_populates="api", cascade="all, delete-orphan", lazy="dynamic")
    changes = relationship("APIChange", back_populates="api", cascade="all, delete-orphan", lazy="dynamic")
    
    # Indexes for performance
    __table_args__ = (
        UniqueConstraint('service_name', 'version', name='uq_api_service_version'),
        Index('idx_api_status_created', 'status', 'created_at'),
        Index('idx_api_owner_status', 'owner_team', 'status'),
        {'comment': 'Core API entity for lifecycle management'}
    )
    
    def __repr__(self):
        return f"<API(id={self.id}, name='{self.name}', version='{self.version}', status='{self.status.value}')>"


# API Version Model
class APIVersion(Base, BaseModel):
    __tablename__ = "api_versions"
    
    api_id = Column(Integer, ForeignKey("apis.id"), nullable=False)
    version = Column(String(50), nullable=False)
    spec_content = Column(Text)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    api = relationship("API", back_populates="versions")


# API Change Model
class APIChange(Base, BaseModel):
    """
    API Change Model - Records changes between API versions
    
    Tracks version transitions, change types, and detailed change information
    for governance, auditing, and impact analysis.
    """
    __tablename__ = "api_changes"
    
    # Foreign key relationship
    api_id = Column(Integer, ForeignKey("apis.id", ondelete="CASCADE"), nullable=False, index=True, comment="Reference to the API")
    
    # Version tracking
    from_version = Column(String(50), nullable=True, comment="Source version (null for initial version)")
    to_version = Column(String(50), nullable=False, index=True, comment="Target/current version")
    
    # Change metadata
    change_type = Column(SQLEnum(ChangeType), nullable=False, index=True, comment="Type of change: breaking, non_breaking, or addition")
    description = Column(Text, nullable=False, comment="Human-readable description of what changed")
    details = Column(Text, nullable=True, comment="Detailed change information in JSON format (diffs, impacts, etc.)")
    
    # Relationships
    api = relationship("API", back_populates="changes")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_change_type_created', 'change_type', 'created_at'),
        Index('idx_change_api_versions', 'api_id', 'from_version', 'to_version'),
        Index('idx_change_to_version', 'to_version'),
        {'comment': 'API change tracking for version management and governance'}
    )
    
    def __repr__(self):
        return f"<APIChange(id={self.id}, api_id={self.api_id}, {self.from_version or 'initial'}->{self.to_version}, type='{self.change_type.value}')>"


# Governance Policy Model
class GovernancePolicy(Base, BaseModel):
    __tablename__ = "governance_policies"
    
    name = Column(String(255), nullable=False)
    description = Column(Text)
    rule_type = Column(String(100))
    rule_config = Column(Text)  # JSON field for rule configuration
    is_active = Column(Boolean, default=True)
    severity = Column(String(50))  # critical, warning, info
