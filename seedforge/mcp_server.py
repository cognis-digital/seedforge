"""SEEDFORGE MCP server — exposes generate() as an MCP tool."""
from __future__ import annotations
import json
import sys

from seedforge.core import generate, SeedForgeError


def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-seedforge[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print(
            "Install the MCP extra: pip install 'cognis-seedforge[mcp]'",
            file=sys.stderr,
        )
        return 1
    app = FastMCP("seedforge")

    @app.tool()
    def seedforge_generate(schema: str, seed: int = 0) -> str:
        """Generate synthetic test data from a JSON schema string.

        Args:
            schema: JSON-encoded schema object with a 'tables' key.
            seed: integer master seed for deterministic output (default 0).

        Returns:
            JSON-encoded dict mapping table names to lists of row dicts.
        """
        try:
            schema_dict = json.loads(schema)
        except json.JSONDecodeError as exc:
            raise ValueError(f"schema must be valid JSON: {exc}") from exc
        try:
            data = generate(schema_dict, seed=seed)
        except SeedForgeError as exc:
            raise ValueError(str(exc)) from exc
        return json.dumps(data, default=str)

    app.run()
    return 0
