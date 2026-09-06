# special-export-mcp

Standalone MCP server. Fetches Wikipedia page wikitext through
`Special:Export` and parses wikitables out of it into structured rows.

Status: under construction. See [docs/specs](docs/specs/README.md) for the
full design.

## Data integrity

Wikipedia can contain structurally broken tables. Results therefore carry
machine-readable `warnings`; consumers and AI agents must inspect them before
persisting positional row data. Ambiguous rows are returned as evidence but
must be quarantined rather than silently corrected. See
[Data integrity and recovery](docs/data-integrity.md) for the required fallback
policy and the known Golf Mk4 example.

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
