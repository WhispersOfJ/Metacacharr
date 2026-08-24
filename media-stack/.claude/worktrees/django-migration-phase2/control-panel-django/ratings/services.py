import os

import httpx

from core.api_base import ServiceError


def get_imdb_rating(imdb_id: str) -> dict:
    api_key = os.environ.get("OMDB_KEY")
    if not api_key:
        raise ServiceError("OMDB_KEY is not configured", status=500)
    try:
        response = httpx.get(
            "https://www.omdbapi.com/", params={"apikey": api_key, "i": imdb_id}, timeout=10
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ServiceError(f"OMDb request failed: {exc}") from exc
    data = response.json()
    if data.get("Response") != "True":
        raise ServiceError(data.get("Error", "No match found"), status=404)
    rating = data.get("imdbRating")
    if not rating or rating == "N/A":
        raise ServiceError(f'"{data.get("Title")}" has no IMDb rating yet.', status=404)
    return {
        "imdbId": imdb_id,
        "title": data.get("Title"),
        "year": data.get("Year"),
        "rating": rating,
        "votes": data.get("imdbVotes"),
    }


def get_mdblist_rating(imdb_id: str) -> dict:
    api_key = os.environ.get("MDBLIST_KEY")
    if not api_key:
        raise ServiceError("MDBLIST_KEY is not configured", status=500)
    try:
        response = httpx.get(
            "https://mdblist.com/api/", params={"apikey": api_key, "i": imdb_id}, timeout=10
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ServiceError(f"MDBList request failed: {exc}") from exc
    data = response.json()
    if data.get("response") is False:
        raise ServiceError(data.get("error", "No match found"), status=404)
    # MDBList fuzzy-matches an unrecognized-but-well-formed id to an
    # unrelated title instead of erroring, and even echoes the requested
    # id back as "imdbid" on that garbage match. A real rating always
    # carries a vote count; a garbage match's imdb entry has null votes
    # even when it has a 0 "value" - that combination is the actual tell.
    imdb_entry = next((x for x in data.get("ratings", []) if x.get("source") == "imdb"), None)
    has_real_imdb_rating = bool(imdb_entry and imdb_entry.get("votes"))
    score = data.get("score")
    if (score is None or score < 0) and not has_real_imdb_rating:
        raise ServiceError(f'"{data.get("title")}" has no rating on MDBList yet.', status=404)
    return {
        "imdbId": imdb_id,
        "title": data.get("title"),
        "year": data.get("year"),
        "score": score,
        "imdbRating": imdb_entry.get("value") if imdb_entry else None,
        "imdbVotes": imdb_entry.get("votes") if imdb_entry else None,
    }
