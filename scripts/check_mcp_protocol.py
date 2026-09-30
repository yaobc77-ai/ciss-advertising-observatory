"""Read-only real stdio MCP check against the configured local collection."""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import Client, StdioServerParameters


async def check():
    server = StdioServerParameters(
        command=sys.executable, args=["-m", "observatory.mcp_server", "--dataset", "native"],
        env={**os.environ, "OPENAI_API_KEY": ""},
    )
    async with Client(server, mode="legacy") as client:
        tools = await client.list_tools()
        assert len(tools.tools) == 7
        stats = (await client.call_tool("record_statistics", {
            "filters": {"publishers": ["The Washington Post"]}, "group_by": "sponsors",
        })).structured_content
        assert stats["status"] == "ok"
        assert sum(row["count"] for row in stats["groups"]) == stats["collections"][0]["total"]
        record_id = stats["records"][0]["record_id"]
        graph = (await client.call_tool("get_graph_neighborhood", {"record_id": record_id, "limit": 1})).structured_content
        sources = (await client.call_tool("get_record_sources", {"record_id": record_id})).structured_content
        assert graph["status"] == sources["status"] == "ok"
        assert graph["graph"]["records"][0]["record_id"] == sources["record"]["record_id"]
        rejected = await client.call_tool("record_statistics", {"sql": "SELECT secret"})
        assert rejected.is_error
        return {"status": "passed", "transport": "stdio", "real_subprocess": True,
                "database": "configured_local_collection", "model_calls": 0,
                "tools": [tool.name for tool in tools.tools], "data_version": stats["data_version"],
                "statistics": {"collections": stats["collections"], "groups": stats["groups"]},
                "record_id": record_id, "version_id": sources["record"]["version_id"],
                "source_refs": sources["source_refs"], "source_artifacts": len(sources["source_artifacts"]),
                "graph_nodes": len(graph["graph"]["nodes"]), "graph_edges": len(graph["graph"]["edges"]),
                "extra_sql_argument_rejected": True}


if __name__ == "__main__":
    report = asyncio.run(check())
    Path("reports/mcp_protocol_smoke_20260929.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
