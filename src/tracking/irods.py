import re
import json
import yaml 
import logging
from irods.session import iRODSSession
from collections import Counter, defaultdict
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Pattern, Dict, Set, Literal, Optional, Any
from datetime import datetime
from pathlib import PurePosixPath

ISSUE_LEVELS: Dict[str, int] = {
    "name_mismatch":          logging.ERROR,
    "missing_files":          logging.ERROR,
    "unexpected_files":       logging.WARNING,
    "missing_collections":    logging.ERROR,
    "too_many_collections":   logging.ERROR,
    "unexpected_collections": logging.WARNING,
    "missing_metadata_keys":  logging.ERROR,
}

def load_schema_from_file(path: str) -> 'CollectionSchema':
    """
    Load a CollectionSchema from a YAML or JSON file.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return CollectionSchema.model_validate(data)


def load_collection_from_irods(session: iRODSSession, path: str) -> 'IrodsCollection':
    """
    Load an IrodsCollection tree from iRODS starting at `path`.
    """
    irods_coll = session.collections.get(path)
    return IrodsCollection.from_irods(irods_coll)

def log_validation_report(
    report: 'ValidationReport',
    *,
    logger: Optional[logging.Logger] = None,
    as_json: bool = False,
) -> None:
    """
    Log all issues in a ValidationReport plus a summary line.
    """
    if logger is None:
        logger = logging.getLogger("irods.validation")

    for issue in report.issues:
        level = ISSUE_LEVELS.get(issue.kind, logging.INFO)

        if as_json:
            payload = {
                "path": issue.path,
                "kind": issue.kind,
                "message": issue.message,
                "details": issue.details,
            }
            logger.log(level, json.dumps(payload, ensure_ascii=False))
        else:
            msg = f"{issue.path} | {issue.kind}: {issue.message}"
            if issue.details:
                msg += f" | details={issue.details}"
            logger.log(level, msg)

    counts = Counter(i.kind for i in report.issues)
    summary = ", ".join(f"{k}={counts[k]}" for k in sorted(counts)) or "no issues"
    status = "PASSED" if report.ok else "FAILED"
    logger.info("Validation %s (%s)", status, summary)

class NameRule(BaseModel):
    """
    Represents a naming rule with a regex pattern and occurrence constraints.
    """
    pattern: Pattern[str]
    min: int = 1
    max: Optional[int] = None
    description: Optional[str] = None

    @field_validator("pattern", mode="before")
    @classmethod
    def compile_pattern(cls, v):
        return re.compile(v) if isinstance(v, str) else v


class IrodsCollection(BaseModel):
    """
    Represents an iRODS collection with metadata, sub-collections, and data objects.
    """
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    name: str
    path: PurePosixPath
    create_time: datetime
    modify_time: datetime
    metadata: Dict[str, List[str]] = Field(default_factory=dict)
    collections: List['IrodsCollection'] = Field(default_factory=list)
    data_objects: List[str] = Field(default_factory=list)

    @classmethod
    def from_irods(cls, irods_collection) -> 'IrodsCollection':
        metadata: Dict[str, List[str]] = defaultdict(list)
        for avu in irods_collection.metadata.items():
            metadata.setdefault(avu.name, []).append(avu.value)
        
        return cls(
            name=irods_collection.name,
            path=irods_collection.path,
            create_time=irods_collection.create_time,
            modify_time=irods_collection.modify_time,
            metadata=dict(metadata),
            collections=[cls.from_irods(c) for c in irods_collection.subcollections],
            data_objects=[obj.name for obj in irods_collection.data_objects]
        )
    

class CollectionSchema(BaseModel):
    name: 'NameRule' = Field(default_factory=lambda: NameRule(pattern=re.compile(r'.*'), min=1, max=None))
    metadata_keys: Set[str] = Field(default_factory=set)
    data_objects: List['NameRule'] = Field(default_factory=list)
    collections: List['CollectionSchema'] = Field(default_factory=list)
    allow_extra_files: bool = False
    allow_extra_collections: bool = False


class ValidationIssue(BaseModel):
    """
    Represents a validation issue found during schema validation.
    """
    path: str
    kind: Literal[
        "name_mismatch", "missing_files", "unexpected_files",
        "missing_collections", "too_many_collections", "unexpected_collections",
        "missing_metadata_keys"
    ]
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    """
    Represents the result of validating an iRODS collection against a schema.
    """
    ok: bool
    issues: List['ValidationIssue'] = Field(default_factory=list)


def validate_collection(collection: IrodsCollection, schema: CollectionSchema) -> ValidationReport:
    issues: List[ValidationIssue] = []

    # Name
    if not schema.name.pattern.fullmatch(collection.name):
        issues.append(ValidationIssue(
            path=str(collection.path),
            kind="name_mismatch",
            message=f"Collection name '{collection.name}' does not match pattern '{schema.name.pattern.pattern}'"
        ))
    
    # Metadata
    missing_keys = sorted(schema.metadata_keys - set(collection.metadata.keys()))
    if missing_keys:
        issues.append(ValidationIssue(
            path=str(collection.path),
            kind="missing_metadata_keys",
            message=f"Missing metadata keys: {', '.join(missing_keys)}",
            details={"missing_keys": missing_keys}
        ))
    
    # Data Objects
    data_object_names = set(collection.data_objects)
    used_files: Set[str] = set()
    for rule in schema.data_objects:
        matches = sorted([name for name in data_object_names if rule.pattern.fullmatch(name)])
        if len(matches) < rule.min:
            issues.append(ValidationIssue(
                path=str(collection.path),
                kind="missing_files",
                message=f"Expected at least {rule.min} files matching '{rule.pattern.pattern}', found {len(matches)}",
                details={"expected_pattern": rule.pattern.pattern, "found": matches}
            ))
        if rule.max is not None and len(matches) > rule.max:
            issues.append(ValidationIssue(
                path=str(collection.path),
                kind="unexpected_files",
                message=f"Expected at most {rule.max} files matching '{rule.pattern.pattern}', found {len(matches)}",
                details={"expected_pattern": rule.pattern.pattern, "found": matches}
            ))
        used_files.update(matches)
    
    if not schema.allow_extra_files:
        unexpected_files = sorted(data_object_names - used_files)
        if unexpected_files:
            issues.append(ValidationIssue(
                path=str(collection.path),
                kind="unexpected_files",
                message=f"Unexpected files found: {', '.join(unexpected_files)}",
                details={"unexpected_files": unexpected_files}
            ))
    
    # Collections
    collection_names = {col.name: col for col in collection.collections}
    used_collections: Set[str] = set()

    for child_schema in schema.collections:
        matches = [col for name, col in collection_names.items() if child_schema.name.pattern.fullmatch(name)]
        if len(matches) < child_schema.name.min:
            issues.append(ValidationIssue(
                path=str(collection.path),
                kind="missing_collections",
                message=f"Expected at least {child_schema.name.min} collections matching '{child_schema.name.pattern.pattern}', found {len(matches)}",
                details={"expected_pattern": child_schema.name.pattern.pattern, "found": [col.name for col in matches]}
            ))
        if child_schema.name.max is not None and len(matches) > child_schema.name.max:
            issues.append(ValidationIssue(
                path=str(collection.path),
                kind="too_many_collections",
                message=f"Expected at most {child_schema.name.max} collections matching '{child_schema.name.pattern.pattern}', found {len(matches)}",
                details={"expected_pattern": child_schema.name.pattern.pattern, "found": [col.name for col in matches]}
            ))
        
        # Recursive validation
        for col in matches:
            used_collections.add(col.name)
            subreport = validate_collection(col, child_schema)
            issues.extend(subreport.issues)
    
    if not schema.allow_extra_collections:
        unexpected_collections = sorted(set(collection_names.keys()) - used_collections)
        if unexpected_collections:
            issues.append(ValidationIssue(
                path=str(collection.path),
                kind="unexpected_collections",
                message=f"Unexpected collections found: {', '.join(unexpected_collections)}",
                details={"unexpected_collections": unexpected_collections}
            ))
    
    return ValidationReport(ok=len(issues) == 0, issues=issues)
