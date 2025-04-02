import logging

import falcon
import httpx

from ecfr import urls
from ecfr.logs import log_errors
from ecfr.services import TitleService
from ecfr.timestamps import nowIso8601

logger = logging.getLogger("ecfr")


class HealthResource:
    """Health resource for determining that a container is live"""

    auth = {"auth_disabled": True}

    @log_errors
    async def on_get(self, req, resp):
        resp.status = falcon.HTTP_OK
        resp.media = {"message": f"Health is okay. Time is {nowIso8601()}"}


class WordCountResource:
    """Analyzing word count per agency from eCFR Titles"""

    auth = {"auth_disabled": True}

    @log_errors
    async def on_get(self, req, resp):
        # Read the request body
        r = httpx.get(f"{urls.ADMN_URL}/agencies.json")
        agencies = r.json()["agencies"]

        agency_names = [item['short_name'] for item in agencies]

        # Count words
        agency_count = len(agency_names)

        # Prepare the response
        resp.status = falcon.HTTP_OK
        resp.content_type = "application/json"
        resp.media = {
            "agency_count": agency_count,
            "agencies": agency_names
        }

class TitlesResource:
    """Gets and stores all titles and all sections in each title."""
    auth = {"auth_disabled": True}

    def __init__(self, title_service: TitleService):
        self.title_service = title_service

    @log_errors
    async def on_get(self, req, resp):
        params = req.params
        titles = await self.title_service.get_titles()
        if "get_all" in params and params["get_all"] == "true":
            await self.title_service.populate_title_sections()

        # Prepare the response
        resp.status = falcon.HTTP_OK
        resp.content_type = "application/json"
        resp.media = await self.title_service.get_counts()

async def call_url(url, client: httpx.AsyncClient) -> httpx.Response | None:
    """Call a URL and return the response"""
    response = await client.get(url, timeout=30.00)
    if response.status_code != 200:
        logger.error(f"Failed to retrieve {url}: {response.status_code}")
        return None
    return response

class TitleCountsResource:
    """Gets word counts for all titles"""
    auth = {"auth_disabled": True}

    def __init__(self, title_service: TitleService):
        self.title_service = title_service

    @log_errors
    async def on_get(self, req, resp):
        # Read the request body
        titles_json = await self.title_service.get_titles()
        titles = [str(title_json["number"]) for title_json in titles_json]

        counts = [await self.title_service.get_title_words(title) for title in titles]

        # Prepare the response
        resp.status = falcon.HTTP_OK
        resp.content_type = "application/json"
        resp.media = counts

class SectionCountsResource:
    """Gets word counts for all sections"""
    auth = {"auth_disabled": True}

    def __init__(self, title_service: TitleService):
        self.title_service = title_service

    @log_errors
    async def on_get(self, req, resp):
        # Read the request body
        titles_json = await self.title_service.get_titles()
        titles = [str(title_json["number"]) for title_json in titles_json]

        counts = [await self.title_service.get_title_word_count_by_sections(title) for title in titles]

        # Prepare the response
        resp.status = falcon.HTTP_OK
        resp.content_type = "application/json"
        resp.media = counts

class TitleCountResource:
    """Gets word count per title"""

    auth = {"auth_disabled": True}

    def __init__(self, title_service: TitleService):
        self.title_service = title_service

    @log_errors
    async def on_get(self, req, resp, title):
        # Read the request body
        if title is None:
            resp.status = falcon.HTTP_BAD_REQUEST
            resp.media = {"error": "Title is required"}
            return

        # Prepare the response
        resp.status = falcon.HTTP_OK
        resp.content_type = "application/json"
        resp.media = await self.title_service.get_title_words(title)

