# Fixtures

Full, unmodified MediaWiki export XML. Committed so tests never hit the network.

| File | Source URL | Fetched |
|---|---|---|
| `volkswagen_golf_mk4.xml` | https://en.wikipedia.org/wiki/Special:Export/Volkswagen_Golf_Mk4 | 2026-09-05 |

Refetch:

```bash
curl -s -A "special-export-mcp/0.1 (https://github.com/Mirza404/special-export-mcp)" \
  "https://en.wikipedia.org/wiki/Special:Export/Volkswagen_Golf_Mk4" \
  -o tests/fixtures/volkswagen_golf_mk4.xml
```

Articles change. Assert on structural invariants, not byte-exact output.
See `docs/specs/007-testing.md`.
