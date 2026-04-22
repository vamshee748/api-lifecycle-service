# DB models
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base
import enum


# Enums for API lifecycle states
class APIStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class ChangeType(str, enum.Enum):
    BREAKING = "breaking"
    NON_BREAKING = "non_breaking"
    ADDITION = "addition"


# Base model class with common fields
class BaseModel:
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# API Model
class API(Base, BaseModel):
    __tablename__ = "apis"
    
    name = Column(String(255), nullable=False, index=True)
    service_name = Column(String(255), nullable=False)
    version = Column(String(50), nullable=False)
    status = Column(SQLEnum(APIStatus), default=APIStatus.DRAFT)
    description = Column(Text)
    base_url = Column(String(500))
    spec_url = Column(String(500))
    owner_team = Column(String(255))
    
    # Relationships
    versions = relationship("APIVersion", back_populates="api")
    changes = relationship("APIChange", back_populates="api")


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
    __tablename__ = "api_changes"
    
    api_id = Column(Integer, ForeignKey("apis.id"), nullable=False)
    from_version = Column(String(50))
    to_version = Column(String(50))
    change_type = Column(SQLEnum(ChangeType))
    description = Column(Text)
    details = Column(Text)  # JSON field for detailed diff
    
    # Relationships
    api = relationship("API", back_populates="changes")


# Governance Policy Model
class GovernancePolicy(Base, BaseModel):
    __tablename__ = "governance_policies"
    
    name = Column(String(255), nullable=False)
    description = Column(Text)
    rule_type = Column(String(100))
    rule_config = Column(Text)  # JSON field for rule configuration
    is_active = Column(Boolean, default=True)
    severity = Column(String(50))  # critical, warning, info
