"""Sheets (CP-31, Striver A2Z) and user collections."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.errors import ValidationError
from app.schemas.requests import CollectionItemRequest, CollectionRequest
from app.services import sheet_service

router = APIRouter(tags=["sheets"])


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValidationError("problem_id must be a UUID") from exc


@router.get("/sheets")
def list_sheets(db: DbSession, user: CurrentUser) -> list[dict]:
    return sheet_service.list_sheets(db, user.id)


@router.get("/sheets/{slug}")
def sheet_detail(slug: str, db: DbSession, user: CurrentUser) -> dict:
    return sheet_service.sheet_detail(db, user.id, slug)


@router.get("/sheets/{slug}/problems")
def sheet_problems(
    slug: str,
    db: DbSession,
    user: CurrentUser,
    section: str | None = None,
    status: str | None = None,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    return sheet_service.sheet_problems(
        db, user.id, slug, section=section, status=status, limit=limit, offset=offset
    )


@router.get("/collections")
def list_collections(db: DbSession, user: CurrentUser) -> list[dict]:
    return sheet_service.list_collections(db, user.id)


@router.post("/collections", status_code=201)
def create_collection(
    payload: CollectionRequest, db: DbSession, user: CurrentUser
) -> dict:
    collection = sheet_service.create_collection(
        db,
        user.id,
        payload.name,
        description=payload.description,
        color=payload.color,
        icon=payload.icon,
    )
    return {
        "id": str(collection.id),
        "slug": collection.slug,
        "name": collection.name,
        "count": 0,
    }


@router.get("/collections/{slug}")
def collection_problems(slug: str, db: DbSession, user: CurrentUser) -> dict:
    collection = sheet_service.require_collection(db, user.id, slug)
    return {
        "slug": collection.slug,
        "name": collection.name,
        "description": collection.description,
        "is_system": collection.is_system,
        "items": sheet_service.collection_problems(db, user.id, slug),
    }


@router.post("/collections/{slug}/problems", status_code=201)
def add_to_collection(
    slug: str, payload: CollectionItemRequest, db: DbSession, user: CurrentUser
) -> dict:
    item = sheet_service.add_to_collection(
        db, user.id, slug, _uuid(payload.problem_id), payload.note
    )
    return {"collection": slug, "problem_id": str(item.problem_id)}


@router.delete("/collections/{slug}/problems/{problem_id}")
def remove_from_collection(
    slug: str, problem_id: str, db: DbSession, user: CurrentUser
) -> dict:
    sheet_service.remove_from_collection(db, user.id, slug, _uuid(problem_id))
    return {"removed": problem_id}
