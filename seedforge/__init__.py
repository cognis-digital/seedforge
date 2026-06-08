"""SEEDFORGE - Synthetic test-data generator with referential integrity.

Deterministic, dependency-free fake data for databases and APIs. Define tables
in a JSON schema, declare foreign keys, and SEEDFORGE generates rows whose
relationships actually hold together (every FK points at a real PK).
"""
from .core import (
    Schema,
    Generator,
    SeedForgeError,
    SchemaError,
    generate,
    FIELD_TYPES,
)

TOOL_NAME = "seedforge"
TOOL_VERSION = "1.0.0"

__all__ = [
    "Schema",
    "Generator",
    "SeedForgeError",
    "SchemaError",
    "generate",
    "FIELD_TYPES",
    "TOOL_NAME",
    "TOOL_VERSION",
]
