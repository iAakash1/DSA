"""Sheet import pipeline.

Imports are declarative and idempotent: running the same file twice imports
nothing new the second time. Every row is validated, duplicates collapse onto
the canonical problem, and the caller gets a report rather than a silent
success.

Import file format (see `docs/database.md` and `data/seed/*.json`):

    {
      "sheet":    {"slug", "name", "description", "kind", "source_url"},
      "sections": [{"slug", "name", "kind", "rating_bucket", "topic"}],
      "problems": [{"platform", "external_id" | "url", "title", "rating",
                    "difficulty", "tags", "section", "topics", "patterns"}]
    }

Metadata in the file is treated as a *hint*. When the platform archive is
reachable it wins, because it is authoritative and always current.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ValidationError
from app.core.logging import get_logger
from app.integrations.base import IntegrationError
from app.integrations.codeforces import CodeforcesClient
from app.models.enums import Platform, SectionKind, SheetKind
from app.models.problem import Problem, Topic
from app.models.sheet import Sheet, SheetProblem, SheetSection
from app.services.problem_service import apply_taxonomy, get_or_create_problem
from app.utils.timeutils import utcnow
from app.utils.normalize import (
    NormalizationError,
    parse_problem_reference,
    rating_bucket,
    slugify,
)

log = get_logger(__name__)


@dataclass
class ImportReport:
    sheet: str = ""
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    duplicates_merged: int = 0
    removed: int = 0
    sections_created: int = 0
    metadata_enriched: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sheet": self.sheet,
            "imported": self.imported,
            "updated": self.updated,
            "skipped": self.skipped,
            "duplicates_merged": self.duplicates_merged,
            "removed": self.removed,
            "sections_created": self.sections_created,
            "metadata_enriched": self.metadata_enriched,
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def summary(self) -> str:
        return (
            f"Imported: {self.imported}  Updated: {self.updated}  "
            f"Skipped: {self.skipped}  Duplicates merged: {self.duplicates_merged}  "
            f"Errors: {len(self.errors)}"
        )


def load_import_file(path: str | Path) -> dict[str, Any]:
    """Read and validate an import file.

    Paths are resolved and confined to the repository so a malicious import
    payload cannot be used to read arbitrary files.
    """
    from app.core.config import REPO_ROOT

    resolved = Path(path).expanduser().resolve()
    if not str(resolved).startswith(str(REPO_ROOT.resolve())):
        raise ValidationError("Import files must live inside the project directory")
    if not resolved.exists():
        raise ValidationError(f"Import file not found: {resolved}")

    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{resolved.name} is not valid JSON: {exc}") from exc

    # Native format passes through; anything else is adapted by the caller,
    # which knows which sheet the file belongs to.
    return payload


#: Bump when parsing behaviour changes, so a stored corpus can be traced to
#: the exact code that produced it.
PARSER_VERSION = "1.1.0"


def source_fingerprint(payload: Any) -> str:
    """Stable SHA-256 of a source payload, for provenance and change detection."""
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def import_sheet(
    db: Session,
    payload: dict[str, Any],
    *,
    enrich: bool = True,
    provenance: dict[str, Any] | None = None,
    reconcile: bool = False,
) -> ImportReport:
    """Import (or re-import) one sheet.

    `reconcile=True` treats the payload as the complete authoritative corpus:
    memberships for problems absent from it are removed, so a stale
    development seed cannot inflate the sheet. The canonical problems
    themselves are never deleted — they may carry another sheet's membership,
    user progress, notes or hints.
    """
    report = ImportReport()

    sheet_spec = payload.get("sheet") or {}
    slug = sheet_spec.get("slug")
    name = sheet_spec.get("name")
    if not slug or not name:
        raise ValidationError("The 'sheet' object requires both 'slug' and 'name'")
    report.sheet = slug

    sheet = db.scalar(select(Sheet).where(Sheet.slug == slug))
    if sheet is None:
        sheet = Sheet(
            slug=slug,
            name=name,
            description=sheet_spec.get("description"),
            kind=sheet_spec.get("kind", SheetKind.CUSTOM),
            source_url=sheet_spec.get("source_url"),
            sort_order=sheet_spec.get("order", 0),
        )
        db.add(sheet)
        db.flush()
    else:
        sheet.name = name
        sheet.description = sheet_spec.get("description", sheet.description)
        sheet.source_url = sheet_spec.get("source_url", sheet.source_url)

    if provenance:
        sheet.source_metadata = {
            **(provenance or {}),
            "parser_version": PARSER_VERSION,
            "imported_at": utcnow().isoformat(),
        }
        sheet.source_url = provenance.get("source_url", sheet.source_url)

    sections = _upsert_sections(db, sheet, payload.get("sections") or [], report)

    archive: dict[str, dict[str, Any]] = {}
    problems = payload.get("problems") or []
    if enrich and any(
        (p.get("platform") or "").lower() == Platform.CODEFORCES
        or "codeforces.com" in str(p.get("url", "")).lower()
        for p in problems
    ):
        archive = _load_codeforces_archive(report)

    #: canonical id -> the membership it resolved to, so a second row for the
    #: same problem can be recorded on it instead of discarded.
    seen_problem_ids: dict[str, SheetProblem] = {}
    seen_problem_uuids: set[Any] = set()

    for index, spec in enumerate(problems):
        try:
            _import_problem(
                db,
                sheet,
                sections,
                spec,
                index,
                archive,
                report,
                seen_problem_ids,
                seen_problem_uuids,
            )
        except ValidationError as exc:
            report.errors.append(f"[{index}] {exc.message}")
        except NormalizationError as exc:
            report.errors.append(f"[{index}] {exc}")

    if reconcile:
        keep = {
            p.id
            for p in db.scalars(
                select(Problem).where(Problem.id.in_(seen_problem_uuids))
            ).all()
        } if seen_problem_uuids else set()
        stale = [
            link
            for link in db.scalars(
                select(SheetProblem).where(SheetProblem.sheet_id == sheet.id)
            ).all()
            if link.problem_id not in keep
        ]
        for link in stale:
            db.delete(link)
        report.removed = len(stale)
        if stale:
            report.warnings.append(
                f"removed {len(stale)} membership(s) absent from the authoritative "
                "source (canonical problems preserved)"
            )
        db.flush()

        # A restructured source leaves the old sections behind with nothing in
        # them, and an empty section is indistinguishable in the UI from a
        # section the user has not started. Drop the ones this import neither
        # declared nor filled.
        declared = {str(s.get("slug") or slugify(s.get("name", ""))) for s in payload.get("sections") or []}
        emptied = [
            section
            for section in sections.values()
            if section.slug not in declared
            and not db.scalar(
                select(SheetProblem.id)
                .where(SheetProblem.section_id == section.id)
                .limit(1)
            )
        ]
        for section in emptied:
            db.delete(section)
        if emptied:
            report.warnings.append(
                f"removed {len(emptied)} empty section(s) left by the previous "
                f"structure: {', '.join(sorted(s.slug for s in emptied))}"
            )

    if sheet.source_metadata:
        sheet.source_metadata = {
            **sheet.source_metadata,
            "rows_in_source": len(problems),
            "imported": report.imported,
            "updated": report.updated,
            "duplicates_merged": report.duplicates_merged,
            "errors": len(report.errors),
        }

    db.commit()
    log.info("sheet imported", sheet=slug, **{k: v for k, v in report.as_dict().items() if isinstance(v, int)})
    return report


def _upsert_sections(
    db: Session, sheet: Sheet, specs: list[dict[str, Any]], report: ImportReport
) -> dict[str, SheetSection]:
    existing = {
        section.slug: section
        for section in db.scalars(
            select(SheetSection).where(SheetSection.sheet_id == sheet.id)
        ).all()
    }
    topics = {t.slug: t for t in db.scalars(select(Topic)).all()}

    for order, spec in enumerate(specs):
        slug = str(spec.get("slug") or slugify(spec.get("name", "")))
        if not slug:
            report.errors.append(f"Section at position {order} has no slug or name")
            continue

        rating_bucket = spec.get("rating_bucket")
        kind = spec.get(
            "kind",
            SectionKind.RATING_BUCKET if rating_bucket else SectionKind.TOPIC,
        )
        topic = topics.get(spec.get("topic", ""))

        section = existing.get(slug)
        if section is None:
            section = SheetSection(
                sheet_id=sheet.id,
                slug=slug,
                name=spec.get("name", slug),
                kind=kind,
                rating_bucket=rating_bucket,
                sort_order=spec.get("order", order),
                topic_id=topic.id if topic else None,
            )
            db.add(section)
            db.flush()
            existing[slug] = section
            report.sections_created += 1
        else:
            section.name = spec.get("name", section.name)
            section.rating_bucket = rating_bucket
            section.sort_order = spec.get("order", order)
            if topic:
                section.topic_id = topic.id

    return existing


def _load_codeforces_archive(report: ImportReport) -> dict[str, dict[str, Any]]:
    """Authoritative Codeforces metadata, when reachable.

    Failure is fine: the import proceeds using the file's own metadata, and a
    later sync fills in the gaps.
    """
    try:
        archive = CodeforcesClient().fetch_problemset()
        log.info("codeforces archive loaded", problems=len(archive))
        return archive
    except IntegrationError as exc:
        report.warnings.append(
            f"Codeforces metadata unavailable ({exc.message}); "
            "using the ratings supplied in the import file. "
            "Run a sync later to refresh them."
        )
        return {}


#: Fields of a source row worth keeping on the membership when several rows
#: collapse onto one canonical problem.
_ENTRY_FIELDS = ("title", "label", "section", "difficulty")


def _source_entry(spec: dict[str, Any], index: int) -> dict[str, Any]:
    """A compact record of one source row, for `SheetProblem.source_entries`."""
    entry: dict[str, Any] = {"order": spec.get("order", index)}
    for field_name in _ENTRY_FIELDS:
        if spec.get(field_name) is not None:
            entry[field_name] = spec[field_name]
    extra = spec.get("extra") or {}
    for field_name in ("step", "sub_step", "tuf_problem_id", "article_url"):
        if extra.get(field_name):
            entry[field_name] = extra[field_name]
    return entry


def _import_problem(
    db: Session,
    sheet: Sheet,
    sections: dict[str, SheetSection],
    spec: dict[str, Any],
    index: int,
    archive: dict[str, dict[str, Any]],
    report: ImportReport,
    seen: dict[str, SheetProblem],
    seen_uuids: set[Any] | None = None,
) -> None:
    reference = spec.get("url") or spec.get("external_id") or spec.get("slug")
    if not reference:
        raise ValidationError("Each problem needs a 'url', 'external_id' or 'slug'")

    ref = parse_problem_reference(str(reference), spec.get("platform"))
    entry = _source_entry(spec, index)

    existing_link = seen.get(ref.canonical_id)
    if existing_link is not None:
        # The same canonical problem reached from another row of the sheet.
        # Progress collapses onto one problem, but the row is a distinct
        # exercise, so it is recorded rather than dropped.
        existing_link.source_entries = [*(existing_link.source_entries or []), entry]
        report.duplicates_merged += 1
        return

    title = spec.get("title")
    rating = spec.get("rating")
    tags = spec.get("tags") or []
    difficulty = spec.get("difficulty")
    rating_source = "import"

    authoritative = archive.get(ref.external_id)
    if authoritative:
        title = authoritative.get("title") or title
        if authoritative.get("rating"):
            rating = authoritative["rating"]
            rating_source = "codeforces"
        tags = sorted({*tags, *(authoritative.get("tags") or [])})
        report.metadata_enriched += 1

    if rating is not None:
        try:
            rating = int(rating)
        except (TypeError, ValueError):
            raise ValidationError(f"Invalid rating {rating!r} for {ref.canonical_id}")
        if not 0 < rating < 5000:
            raise ValidationError(f"Rating {rating} for {ref.canonical_id} is out of range")

    problem, created = get_or_create_problem(
        db,
        ref,
        title=title,
        rating=rating,
        rating_source=rating_source,
        tags=tags,
        difficulty=difficulty,
        # Platforms without a canonical URL scheme (takeUforward reuses slugs)
        # must be able to supply the real link from the source file.
        url=spec.get("url_override") or spec.get("problem_url"),
        extra=spec.get("extra"),
        taxonomy_source="sheet",
        commit=False,
    )

    # Hints and curator videos are global problem metadata, merged additively
    # so a later import never drops what an earlier one supplied.
    if spec.get("hints"):
        problem.hints = sorted({*(problem.hints or []), *spec["hints"]}, key=str)
    if spec.get("video_links"):
        problem.video_links = sorted({*(problem.video_links or []), *spec["video_links"]})

    # A readable slug for platforms whose identity is not itself readable.
    # takeUforward problems are keyed by a numeric id, which makes a poor
    # search term and a worse URL fragment.
    display_slug = spec.get("display_slug")
    if display_slug and problem.slug in (None, problem.external_id):
        problem.slug = str(display_slug)

    if seen_uuids is not None:
        seen_uuids.add(problem.id)

    if spec.get("topics") or spec.get("patterns"):
        apply_taxonomy(
            db,
            problem,
            topic_slugs=set(spec.get("topics") or []),
            pattern_slugs=set(spec.get("patterns") or []),
            source="sheet",
        )

    section = sections.get(str(spec.get("section", "")))
    if section is None and spec.get("section"):
        report.warnings.append(
            f"{ref.canonical_id} references unknown section {spec['section']!r}"
        )

    # For rating-bucketed sheets, the authoritative rating decides the bucket.
    # This keeps CP-31 correct without hand-maintaining ratings in the file.
    if sheet.kind == SheetKind.CP31 and rating is not None and rating_source == "codeforces":
        # The ceiling comes from the sheet's own sections, not a constant. The
        # helper's default caps at 1700, which silently folded the 1800 and
        # 1900 bands into the 1700 section and left two sections empty once
        # CP-31 grew past that.
        declared = [s.rating_bucket for s in sections.values() if s.rating_bucket]
        bucket = rating_bucket(rating, max_bucket=max(declared) if declared else 1700)
        matching = next(
            (s for s in sections.values() if s.rating_bucket == bucket), None
        )
        if matching is not None and (section is None or section.id != matching.id):
            if section is not None:
                report.warnings.append(
                    f"{ref.canonical_id} moved to the {bucket} bucket "
                    f"(actual rating {rating})"
                )
            section = matching

    link = db.scalar(
        select(SheetProblem).where(
            SheetProblem.sheet_id == sheet.id, SheetProblem.problem_id == problem.id
        )
    )
    if link is None:
        link = SheetProblem(
            sheet_id=sheet.id,
            section_id=section.id if section else None,
            problem_id=problem.id,
            order_index=spec.get("order", index),
            label=spec.get("label"),
            source_entries=[entry],
        )
        db.add(link)
        report.imported += 1
    else:
        link.section_id = section.id if section else link.section_id
        link.order_index = spec.get("order", link.order_index)
        link.label = spec.get("label", link.label)
        # Re-import rebuilds the row list rather than appending to the last
        # run's, so running the importer twice cannot double the entries.
        link.source_entries = [entry]
        report.updated += 1

    seen[ref.canonical_id] = link
    db.flush()


def import_from_path(
    db: Session, path: str | Path, *, enrich: bool = True
) -> ImportReport:
    return import_sheet(db, load_import_file(path), enrich=enrich)

# ---------------------------------------------------------------------------
# Shape-tolerant adapter
# ---------------------------------------------------------------------------

#: Key spellings seen in real exports, per logical field. Being permissive here
#: means a raw API response can be imported unmodified instead of hand-edited
#: into our format — which is where transcription errors creep in.
_IDENTIFIER_KEYS = (
    "url", "problemUrl", "problem_url", "link", "href",
    "external_id", "externalId", "problemId", "problem_id", "slug", "id",
)
_CATEGORY_KEYS = (
    "rating", "level", "bucket", "category", "section", "group", "tag",
    "problemRating", "difficulty_group",
)
_ORDER_KEYS = ("order", "index", "position", "sno", "serial")
_TITLE_KEYS = ("title", "name", "problemName", "problem_name")
_HINT_KEYS = ("hints", "hint", "hintList", "hints_list")
_VIDEO_KEYS = (
    "video", "videoUrl", "video_url", "videoLink", "video_link",
    "youtube", "youtubeUrl", "youtube_link", "editorial", "editorialUrl",
    "solutionVideo", "solution_video", "videos",
)


def _first(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, "", []):
            return value
    return None


def _unwrap(payload: Any) -> list[dict[str, Any]] | None:
    """Find the row list inside an arbitrary export wrapper."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return None
    for key in ("problems", "data", "result", "results", "items", "rows", "questions"):
        value = payload.get(key)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value
        # One level of nesting: {"data": {"problems": [...]}}
        if isinstance(value, dict):
            inner = _unwrap(value)
            if inner:
                return inner
    return None


def adapt_payload(
    payload: Any, *, slug: str, name: str, kind: str
) -> dict[str, Any]:
    """Coerce an arbitrary export into the CP-Forge import format.

    Already-native payloads pass through untouched. Anything else is treated as
    a flat row list, with sections derived from whichever category field the
    export happens to use.
    """
    if isinstance(payload, dict) and "sheet" in payload:
        return payload

    rows = _unwrap(payload)
    if rows is None:
        raise ValidationError(
            "Could not find a list of problems in that file. Expected either the "
            "CP-Forge format ({'sheet': ..., 'problems': [...]}), a bare JSON "
            "array, or a wrapper such as {'data': [...]}. See docs/data-sources.md."
        )

    problems: list[dict[str, Any]] = []
    sections: dict[str, dict[str, Any]] = {}

    for index, row in enumerate(rows):
        identifier = _first(row, _IDENTIFIER_KEYS)
        if identifier is None:
            # Keep the row so the importer reports it rather than dropping it.
            problems.append({"_row": index})
            continue

        category = _first(row, _CATEGORY_KEYS)
        section_slug = None
        if category is not None:
            section_slug = str(category).strip().lower().replace(" ", "-")
            if section_slug not in sections:
                numeric = str(category).strip()
                is_rating = numeric.isdigit()
                sections[section_slug] = {
                    "slug": section_slug,
                    "name": str(category).strip(),
                    "kind": "rating_bucket" if is_rating else "topic",
                    "rating_bucket": int(numeric) if is_rating else None,
                    "order": len(sections),
                }

        entry: dict[str, Any] = {"url": str(identifier)}
        title = _first(row, _TITLE_KEYS)
        if title:
            entry["title"] = str(title)
        order = _first(row, _ORDER_KEYS)
        entry["order"] = int(order) if isinstance(order, (int, str)) and str(order).isdigit() else index
        if section_slug:
            entry["section"] = section_slug
        if row.get("platform"):
            entry["platform"] = str(row["platform"]).lower()

        # Curator-supplied hints and solution videos travel with the problem.
        hints = _first(row, _HINT_KEYS)
        if hints:
            entry["hints"] = [str(h) for h in hints] if isinstance(hints, list) else [str(hints)]
        videos = _first(row, _VIDEO_KEYS)
        if videos:
            entry["video_links"] = (
                [str(v) for v in videos] if isinstance(videos, list) else [str(videos)]
            )
        problems.append(entry)

    return {
        "sheet": {"slug": slug, "name": name, "kind": kind},
        "sections": sorted(sections.values(), key=lambda s: s["order"]),
        "problems": problems,
    }
