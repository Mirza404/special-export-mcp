# special-export-mcp

Standalone MCP server. Fetches Wikipedia page wikitext through
`Special:Export` and parses wikitables out of it into structured rows.

Status: under construction. See [docs/specs](docs/specs/README.md) for the
full design.

## Install

Not published to PyPI. Install from git:

```bash
pip install git+https://github.com/Mirza404/special-export-mcp.git
```

With the MCP server extra:

```bash
pip install "special-export-mcp[mcp] @ git+https://github.com/Mirza404/special-export-mcp.git"
```

## Why

`action=parse` (the live rendering API used by `wikipedia-mcp`) has a low
anonymous rate limit and was observed to enter an hours-long undocumented
lockout. `Special:Export` is a documented, export-style alternative that
was unaffected. See
[docs/specs/000-overview.md](docs/specs/000-overview.md) for the full
rationale.

## License

MIT
