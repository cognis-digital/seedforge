"""SEEDFORGE MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from seedforge.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-seedforge[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-seedforge[mcp]'")
        return 1
    app = FastMCP("seedforge")

    @app.tool()
    def seedforge_scan(target: str) -> str:
        """Synthetic test-data generator with referential integrity. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
