"""Poster quality heuristics for the bulk scan job - Phase 04 of
.claude/plans/control-panel-v3-redesign.plan.md. Given an item's Plex
metadata, its media type, and the raw bytes of its currently-applied
poster, return a list of flag strings. Pure functions, no I/O of their
own (the caller already fetched the bytes/metadata) - same "pure lookup"
isolation as candidates.py.
"""
import io

from PIL import Image

from services.posters.candidates import TMDB_KEY, tmdb_get, tmdb_id_for_item

# Plex/TMDb "original" posters are typically 1000-2000px tall - anything
# under this on the short side is a strong signal of scraped/thumbnail-
# quality source art rather than a real low-quality upload.
MIN_POSTER_DIMENSION = 300
# Plex's generated title-card placeholders are small flat-color images;
# real poster art (even a JPEG-compressed one) is essentially never this
# small, so file size alone is most of the signal - the color check below
# just rules out a genuinely tiny piece of real art landing in this band.
PLACEHOLDER_MAX_BYTES = 15_000
PLACEHOLDER_COLOR_TOLERANCE = 12
# Plex's Stream.languageCode is ISO 639-2 (3-letter); TMDb's iso_639_1 on
# a poster image is ISO 639-1 (2-letter). Only the languages actually
# likely to show up in a Radarr/Sonarr/Bazarr-managed library are mapped -
# an unmapped code just means language_mismatch never fires for that item
# (a missed flag, not a false one).
LANG_639_2_TO_1 = {
    "eng": "en", "jpn": "ja", "fre": "fr", "fra": "fr", "ger": "de", "deu": "de",
    "spa": "es", "ita": "it", "por": "pt", "kor": "ko", "chi": "zh", "zho": "zh",
    "rus": "ru", "dan": "da", "swe": "sv", "nor": "no", "dut": "nl", "nld": "nl",
    "pol": "pl", "tur": "tr", "ara": "ar", "hin": "hi", "tha": "th", "vie": "vi",
}


def _is_placeholder(image_bytes: bytes) -> bool:
    if len(image_bytes) > PLACEHOLDER_MAX_BYTES:
        return False
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        r, g, b = img.resize((1, 1)).getpixel((0, 0))
    except Exception:
        return False
    # Plex's placeholder art is a near-uniform dark grey card - a small
    # file that resizes to near-grey is almost certainly that placeholder,
    # not compressed real art (real posters have far more color variance).
    return abs(r - g) < PLACEHOLDER_COLOR_TOLERANCE and abs(g - b) < PLACEHOLDER_COLOR_TOLERANCE and 20 < r < 90


def _poster_dimensions(image_bytes: bytes) -> tuple[int, int] | None:
    try:
        return Image.open(io.BytesIO(image_bytes)).size
    except Exception:
        return None


def _primary_audio_lang(meta: dict) -> str | None:
    for media in meta.get("Media", []):
        for part in media.get("Part", []):
            for stream in part.get("Stream", []):
                if stream.get("streamType") == 2 and stream.get("selected"):
                    tag = stream.get("languageTag")
                    if tag:
                        return tag.lower()
                    code = stream.get("languageCode")
                    if code:
                        return LANG_639_2_TO_1.get(code.lower())
    return None


def _language_mismatch(meta: dict, media_type: str) -> bool:
    """True when the item's primary audio track language differs from the
    language of TMDb's single highest-voted poster (unfiltered by
    language) - a proxy for "the best-available poster for this title
    skews toward a language the audio isn't in", not a literal read of
    what's applied on Plex (the Plex API doesn't expose that). Silently
    False (never flags) when TMDb isn't configured, the audio language
    can't be determined, or there's nothing to compare against - this
    flag is a bonus signal, not a hard requirement."""
    if not TMDB_KEY:
        return False
    audio_lang = _primary_audio_lang(meta)
    if not audio_lang:
        return False
    try:
        tmdb_id = tmdb_id_for_item(meta, media_type)
        if tmdb_id is None:
            return False
        kind = "movie" if media_type == "movie" else "tv"
        data = tmdb_get(f"/{kind}/{tmdb_id}/images")
    except Exception:
        return False
    posters = data.get("posters") or []
    if not posters:
        return False
    posters.sort(key=lambda p: (p.get("vote_average") or 0, p.get("vote_count") or 0), reverse=True)
    top_lang = posters[0].get("iso_639_1")
    if not top_lang:  # textless art is always a safe match, never flagged
        return False
    return top_lang != audio_lang


def scan_item_quality(meta: dict, media_type: str, poster_bytes: bytes) -> list[str]:
    """Best-first list of quality flags for one item's current poster."""
    if _is_placeholder(poster_bytes):
        return ["placeholder"]  # definitionally also "low res" - no point double-flagging
    flags = []
    dims = _poster_dimensions(poster_bytes)
    if dims and min(dims) < MIN_POSTER_DIMENSION:
        flags.append("low_res")
    if _language_mismatch(meta, media_type):
        flags.append("language_mismatch")
    return flags
