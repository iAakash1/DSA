# Sheet source data

```
data/sources/raw/          RAW authoritative export, exactly as provided — never rewritten
data/sources/normalized/   Deterministic output of the normalizer — regenerable
                           ↓
                    PostgreSQL (canonical problems + sheet memberships)
```

The raw file is the source of truth. If the database is destroyed, the entire
CP-31 and Striver corpus is rebuildable from `raw/` alone — no manual re-entry.

| Path | Contents |
| --- | --- |
| `raw/cp31.json` | complete CP-31 export, byte-for-byte as supplied |
| `raw/striver_a2z.json` | complete Striver A2Z export |
| `normalized/*.normalized.json` | parsed, validated, canonicalised rows |

Place a raw export, then:

```bash
python scripts/import_cp31.py --source data/sources/raw/cp31.json
python scripts/validate_cp31.py
```

The importer never overwrites `raw/`. It writes the normalized artifact and a
provenance record (source hash, parser version, timestamp) onto the sheet.

## Licensing

CP-31 and Striver A2Z are third-party curated sheets. Whether their contents
may be redistributed in this repository depends on those sources' terms. Raw
exports are therefore **gitignored by default** — the repository does not claim
to contain them. Keep them locally and re-import as needed; the counts reported
by the validator tell you exactly what is loaded.
