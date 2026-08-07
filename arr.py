import logging
import os

import aiohttp

log = logging.getLogger(__name__)

RADARR_URL = os.getenv("RADARR_URL", "http://radarr:7878")
RADARR_API_KEY = os.getenv("RADARR_API_KEY")
SONARR_URL = os.getenv("SONARR_URL", "http://sonarr:8989")
SONARR_API_KEY = os.getenv("SONARR_API_KEY")

_TIMEOUT = aiohttp.ClientTimeout(total=10)
# Interactive/manual search queries every configured indexer synchronously and
# can legitimately take much longer than a normal lookup or queue call.
_SEARCH_TIMEOUT = aiohttp.ClientTimeout(total=90)


async def _get(session, url, params, timeout=_TIMEOUT):
    try:
        async with session.get(url, params=params, timeout=timeout) as r:
            if r.status != 200:
                log.warning("GET %s -> HTTP %s", url, r.status)
                return None
            return await r.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError) as e:
        log.warning("GET %s: %s", url, e)
        return None


async def _post(session, url, params, json_body, timeout=_TIMEOUT):
    try:
        async with session.post(url, params=params, json=json_body, timeout=timeout) as r:
            if r.status not in (200, 201):
                log.warning("POST %s -> HTTP %s", url, r.status)
                return None
            return await r.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError) as e:
        log.warning("POST %s: %s", url, e)
        return None


def poster_url(item):
    for img in item.get("images", []):
        if img.get("coverType") == "poster":
            url = img.get("remoteUrl") or img.get("url", "")
            if url.startswith("http"):
                return url
    return None


async def lookup_movie(session, term):
    """Search Radarr for candidate movies matching a free-text title."""
    results = await _get(
        session,
        f"{RADARR_URL}/api/v3/movie/lookup",
        {"apiKey": RADARR_API_KEY, "term": term},
    )
    return results or []


async def lookup_series(session, term):
    """Search Sonarr for candidate shows matching a free-text title."""
    results = await _get(
        session,
        f"{SONARR_URL}/api/v3/series/lookup",
        {"apiKey": SONARR_API_KEY, "term": term},
    )
    return results or []


async def interactive_search_movie(session, movie_id):
    """List release candidates for a movie already known to Radarr."""
    results = await _get(
        session,
        f"{RADARR_URL}/api/v3/release",
        {"apiKey": RADARR_API_KEY, "movieId": movie_id},
        timeout=_SEARCH_TIMEOUT,
    )
    return results or []


async def interactive_search_episode(session, series_id, episode_id):
    """List release candidates for a single episode already known to Sonarr."""
    results = await _get(
        session,
        f"{SONARR_URL}/api/v3/release",
        {"apiKey": SONARR_API_KEY, "seriesId": series_id, "episodeId": episode_id},
        timeout=_SEARCH_TIMEOUT,
    )
    return results or []


async def interactive_search_season(session, series_id, season_number):
    """List release candidates for a whole season already known to Sonarr."""
    results = await _get(
        session,
        f"{SONARR_URL}/api/v3/release",
        {"apiKey": SONARR_API_KEY, "seriesId": series_id, "seasonNumber": season_number},
        timeout=_SEARCH_TIMEOUT,
    )
    return results or []


async def _root_folder(session, is_movie):
    base_url = RADARR_URL if is_movie else SONARR_URL
    api_key = RADARR_API_KEY if is_movie else SONARR_API_KEY
    env_override = os.getenv("RADARR_ROOT_FOLDER" if is_movie else "SONARR_ROOT_FOLDER")
    if env_override:
        return env_override
    folders = await _get(session, f"{base_url}/api/v3/rootfolder", {"apiKey": api_key})
    return folders[0]["path"] if folders else None


async def _quality_profile_id(session, is_movie):
    env_override = os.getenv("RADARR_QUALITY_PROFILE_ID" if is_movie else "SONARR_QUALITY_PROFILE_ID")
    if env_override:
        return int(env_override)
    base_url = RADARR_URL if is_movie else SONARR_URL
    api_key = RADARR_API_KEY if is_movie else SONARR_API_KEY
    profiles = await _get(session, f"{base_url}/api/v3/qualityprofile", {"apiKey": api_key})
    return profiles[0]["id"] if profiles else None


async def add_movie(session, lookup_result):
    """Add a movie lookup result to Radarr, unmonitored and without an automatic search."""
    root_folder = await _root_folder(session, is_movie=True)
    quality_profile_id = await _quality_profile_id(session, is_movie=True)
    if not root_folder or not quality_profile_id:
        log.warning("Cannot add movie: no root folder or quality profile configured")
        return None

    body = dict(lookup_result)
    body["qualityProfileId"] = quality_profile_id
    body["rootFolderPath"] = root_folder
    body["monitored"] = False
    body["addOptions"] = {"searchForMovie": False}

    return await _post(session, f"{RADARR_URL}/api/v3/movie", {"apiKey": RADARR_API_KEY}, body)


async def add_series(session, lookup_result):
    """Add a series lookup result to Sonarr, unmonitored and without an automatic search."""
    root_folder = await _root_folder(session, is_movie=False)
    quality_profile_id = await _quality_profile_id(session, is_movie=False)
    if not root_folder or not quality_profile_id:
        log.warning("Cannot add series: no root folder or quality profile configured")
        return None

    body = dict(lookup_result)
    body["qualityProfileId"] = quality_profile_id
    body["rootFolderPath"] = root_folder
    body["monitored"] = False
    body["seasonFolder"] = True
    body["addOptions"] = {"searchForMissingEpisodes": False, "monitor": "none"}
    for season in body.get("seasons", []):
        season["monitored"] = False

    return await _post(session, f"{SONARR_URL}/api/v3/series", {"apiKey": SONARR_API_KEY}, body)


async def radarr_queue(session):
    """Currently downloading/importing movies known to Radarr."""
    result = await _get(
        session,
        f"{RADARR_URL}/api/v3/queue",
        {"apiKey": RADARR_API_KEY, "pageSize": 50, "includeMovie": "true"},
    )
    return (result or {}).get("records", [])


async def sonarr_queue(session):
    """Currently downloading/importing episodes known to Sonarr."""
    result = await _get(
        session,
        f"{SONARR_URL}/api/v3/queue",
        {"apiKey": SONARR_API_KEY, "pageSize": 50, "includeSeries": "true", "includeEpisode": "true"},
    )
    return (result or {}).get("records", [])


async def grab_release(session, is_movie, release):
    """Push a chosen release from an interactive search to the download client."""
    base_url = RADARR_URL if is_movie else SONARR_URL
    api_key = RADARR_API_KEY if is_movie else SONARR_API_KEY
    body = {"guid": release["guid"], "indexerId": release["indexerId"]}
    return await _post(session, f"{base_url}/api/v3/release", {"apiKey": api_key}, body, timeout=_SEARCH_TIMEOUT)
