# Sheet data sources

CP-Forge will not ship an invented problem corpus. The bundled files in
`data/seed/` are **curated starter sets**, clearly labelled as such, and
`scripts/validate_sheets.py` fails while they are incomplete. This document
records exactly what was investigated so nobody repeats the search.

## CP-31 — status: INCOMPLETE (61 of ~310)

### What the authoritative source is

The sheet lives at <https://www.tle-eliminators.com/cp-sheet>. The page is a
React SPA — the HTML contains no problem data.

Tracing the bundle (`/static/js/main.*.js` → 145 lazy chunks) locates the real
data call in chunk `7150`:

```js
const a = api("/public/cp-sheet");
problems: e => a.get(a.authPath("fetch-problems", e))
```

So the corpus endpoint is:

```
GET https://backend-2.tle-eliminators.com/public/cp-sheet/fetch-problems
```

### Why it was not ingested automatically

The endpoint responds, but rejects programmatic clients:

```json
{"success": false, "errorType": "ForbiddenError",
 "message": "Access Denied: Unverified Origin."}
```

That is an intentional access control. Forging the `Origin`/`Referer` header
would be circumventing it, so the automated ingestion stops here by design.

Community GitHub repositories of "CP-31 solutions" were also rejected as a
source: they are one person's solved subset, not the authoritative sheet, and
substituting them would silently produce a different corpus.

### How to complete it

The sheet is free to view with a TLE account. Export it from **your own**
logged-in session:

1. Open <https://www.tle-eliminators.com/cp-sheet> while signed in.
2. DevTools → Network → filter `fetch-problems`.
3. Right-click the request → *Copy response*.
4. Save it as `data/imports/cp31.json`.
5. Run:

```bash
python scripts/import_cp31.py data/imports/cp31.json
python scripts/validate_sheets.py
```

The importer is shape-tolerant (see below), so the raw API response can be
pasted in unmodified — no hand-editing into our format.

## Striver A2Z — status: INCOMPLETE (80 of ~450)

<https://takeuforward.org/strivers-a2z-dsa-course/strivers-a2z-dsa-course-sheet-2>
is likewise dynamic. The same export-and-import route applies:

```bash
python scripts/import_striver.py data/imports/striver.json
```

Section and sub-section ordering is preserved from the export.

## Accepted import shapes

`scripts/import_cp31.py` and `import_striver.py` accept:

1. **CP-Forge format** — the documented `{sheet, sections, problems}` object.
2. **A bare array** of problem objects.
3. **A wrapped payload** — `{"data": [...]}`, `{"problems": [...]}`,
   `{"result": [...]}` etc., as most APIs return.

Within each row these key spellings are recognised:

| Field | Accepted keys |
| --- | --- |
| identifier | `url`, `problemUrl`, `link`, `href`, `external_id`, `problemId`, `slug`, `id` |
| category | `rating`, `level`, `bucket`, `category`, `section`, `group`, `tag` |
| ordering | `order`, `index`, `position`, `sno` |
| title | `title`, `name`, `problemName` |

Anything unrecognised is reported as an error row rather than dropped, and
titles/ratings/tags are then resolved from the Codeforces and LeetCode APIs, so
the export only has to carry an identifier and a category.

## Provenance

Every import records `source_name`, `source_url`, `imported_at` and a SHA-256
of the source payload on the sheet, so the UI can state which corpus version is
loaded and a re-import from a different version is detectable.
