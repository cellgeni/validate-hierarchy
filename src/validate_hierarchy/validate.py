"""Recursive validation of a `Collection` tree against a `CollectionSchema`."""


from validate_hierarchy.models import (
    Collection,
    CollectionSchema,
    ValidationIssue,
    ValidationReport,
)


def validate_collection(
    collection: Collection, schema: CollectionSchema
) -> ValidationReport:
    """Validate `collection` (and everything below it) against `schema`."""
    issues = _validate(collection, schema)
    return ValidationReport(
        path=str(collection.path), ok=len(issues) == 0, issues=issues
    )


def _validate(
    collection: Collection, schema: CollectionSchema
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    path = str(collection.path)

    # Name
    if not schema.name.pattern.fullmatch(collection.name):
        issues.append(ValidationIssue(
            path=path,
            kind="name_mismatch",
            message=(
                f"Collection name '{collection.name}' does not match pattern "
                f"'{schema.name.pattern.pattern}'"
            ),
        ))

    # Metadata
    missing_keys = sorted(schema.metadata_keys - set(collection.metadata))
    if missing_keys:
        issues.append(ValidationIssue(
            path=path,
            kind="missing_metadata_keys",
            message=f"Missing metadata keys: {', '.join(missing_keys)}",
            details={"missing_keys": missing_keys},
        ))

    # Data objects
    data_object_names = set(collection.data_objects)
    used_files: set[str] = set()
    for rule in schema.data_objects:
        matches = sorted(n for n in data_object_names if rule.pattern.fullmatch(n))
        if len(matches) < rule.min:
            issues.append(ValidationIssue(
                path=path,
                kind="missing_files",
                message=(
                    f"Expected at least {rule.min} files matching "
                    f"'{rule.pattern.pattern}', found {len(matches)}"
                ),
                details={"expected_pattern": rule.pattern.pattern, "found": matches},
            ))
        if rule.max is not None and len(matches) > rule.max:
            issues.append(ValidationIssue(
                path=path,
                kind="too_many_files",
                message=(
                    f"Expected at most {rule.max} files matching "
                    f"'{rule.pattern.pattern}', found {len(matches)}"
                ),
                details={"expected_pattern": rule.pattern.pattern, "found": matches},
            ))
        used_files.update(matches)

    if not schema.allow_extra_files:
        unexpected_files = sorted(data_object_names - used_files)
        if unexpected_files:
            issues.append(ValidationIssue(
                path=path,
                kind="unexpected_files",
                message=f"Unexpected files found: {', '.join(unexpected_files)}",
                details={"unexpected_files": unexpected_files},
            ))

    # Sub-collections
    children = {child.name: child for child in collection.collections}
    used_collections: set[str] = set()

    for child_schema in schema.collections:
        rule = child_schema.name
        matches = [c for name, c in children.items() if rule.pattern.fullmatch(name)]
        if len(matches) < rule.min:
            issues.append(ValidationIssue(
                path=path,
                kind="missing_collections",
                message=(
                    f"Expected at least {rule.min} collections matching "
                    f"'{rule.pattern.pattern}', found {len(matches)}"
                ),
                details={
                    "expected_pattern": rule.pattern.pattern,
                    "found": [c.name for c in matches],
                },
            ))
        if rule.max is not None and len(matches) > rule.max:
            issues.append(ValidationIssue(
                path=path,
                kind="too_many_collections",
                message=(
                    f"Expected at most {rule.max} collections matching "
                    f"'{rule.pattern.pattern}', found {len(matches)}"
                ),
                details={
                    "expected_pattern": rule.pattern.pattern,
                    "found": [c.name for c in matches],
                },
            ))

        for child in matches:
            used_collections.add(child.name)
            issues.extend(_validate(child, child_schema))

    if not schema.allow_extra_collections:
        unexpected_collections = sorted(set(children) - used_collections)
        if unexpected_collections:
            issues.append(ValidationIssue(
                path=path,
                kind="unexpected_collections",
                message=(
                    f"Unexpected collections found: {', '.join(unexpected_collections)}"
                ),
                details={"unexpected_collections": unexpected_collections},
            ))

    return issues
