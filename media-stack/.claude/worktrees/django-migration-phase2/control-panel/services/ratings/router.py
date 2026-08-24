"""IMDb/MDBList rating lookups, ported from app.py (lines ~1441-1503) - this
route was missed during the Phase 3/5 backend migration (evolved-control-panel-backend
plan) and 404'd in production until this port; stack-rating-imdb/stack-rating-mdblist
were broken the whole time.
"""
import os

import httpx
from fastapi import APIRouter, Depends

from core.api_hit_counts import install as install_hit_counter
from core.responses import fail, ok
from core.security import current_user_or_service

router = APIRouter(tags=["ratings"])

install_hit_counter()


def _omdb_key() -> str | None:
    return os.environ.get("OMDB_KEY") or None


def _mdblist_key() -> str | None:
    return os.environ.get("MDBLIST_KEY") or None


@router.get("/api/ratings/imdb")
def rating_imdb(imdb_id: str, _=Depends(current_user_or_service)):
    key = _omdb_key()
    if not key:
        fail("No OMDb API key found (OMDB_KEY not set in .env).", status_code=500)
    try:
        r = httpx.get("https://www.omdbapi.com/", params={"i": imdb_id, "apikey": key}, timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"OMDb request failed: {e}")
    data = r.json()
    if data.get("Response") == "False":
        fail(f"OMDb: {data.get('Error', 'no match for that IMDb id')}", status_code=404)
    rating = data.get("imdbRating")
    if not rating or rating == "N/A":
        fail(f'"{data.get("Title")}" has no IMDb rating yet.', status_code=404)
    return ok(
        f'"{data.get("Title")}" ({data.get("Year")}): {rating}/10 ({data.get("imdbVotes")} votes)',
        imdbId=imdb_id,
        title=data.get("Title"),
        year=data.get("Year"),
        rating=rating,
        votes=data.get("imdbVotes"),
    )


@router.get("/api/ratings/mdblist")
def rating_mdblist(imdb_id: str, _=Depends(current_user_or_service)):
    key = _mdblist_key()
    if not key:
        fail("No MDBList API key found (MDBLIST_KEY not set in .env).", status_code=500)
    try:
        r = httpx.get("https://mdblist.com/api/", params={"apikey": key, "i": imdb_id}, timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        fail(f"MDBList request failed: {e}")
    data = r.json()
    if data.get("response") is False:
        fail(f"MDBList: {data.get('error', 'no match for that IMDb id')}", status_code=404)
    # MDBList fuzzy-matches an unrecognized-but-well-formed id to an
    # unrelated title instead of erroring, and even echoes the requested
    # id back as "imdbid" on that garbage match (confirmed live: a bogus
    # tt0000000 request "matched" an unrelated show, with the response's
    # own "imdbid" field reading back tt0000000) - so imdbid can't be used
    # to detect this. A real rating always carries a vote count; a garbage
    # match's imdb entry has null votes even when it has a 0 "value" - that
    # combination is the actual tell.
    imdb_entry = next((x for x in data.get("ratings", []) if x.get("source") == "imdb"), None)
    has_real_imdb_rating = bool(imdb_entry and imdb_entry.get("votes"))
    score = data.get("score")
    if (score is None or score < 0) and not has_real_imdb_rating:
        fail(f'"{data.get("title")}" has no rating on MDBList yet.', status_code=404)
    message = f'"{data.get("title")}" ({data.get("year")}): MDBList score {score}/100'
    if imdb_entry and imdb_entry.get("value") is not None:
        message += f', IMDb {imdb_entry["value"]}/10 ({imdb_entry.get("votes")} votes)'
    return ok(
        message,
        imdbId=imdb_id,
        title=data.get("title"),
        year=data.get("year"),
        score=score,
        imdbRating=imdb_entry.get("value") if imdb_entry else None,
        imdbVotes=imdb_entry.get("votes") if imdb_entry else None,
    )
