import asyncio
import logging
import re
import shelve
from shelve import DbfilenameShelf

import httpx
from lxml import etree

from ecfr import urls

logger = logging.getLogger("ecfr")

TITLE_DATE="2025-03-31"

class TitleService:
    """
    TitleService is responsible for retrieving and caching titles and sections from the eCFR API.
    """
    TITLES_KEY = "titles"
    def __init__(self, client: httpx.AsyncClient, cache: shelve.Shelf):
        self.client: httpx.AsyncClient = client
        self.cache: shelve.Shelf = cache

    async def populate_title_sections(self):
        """Retrieve all sections from all titles in the eCFR API and store in a local cache"""
        titles_json = await self.get_titles()

        for title_json in titles_json:
            title = str(title_json["number"])
            await self.get_title_sections(title)
            if title not in self.cache:
                versions_resp = await self.client.get(
                    f"{urls.VRSN_URL}/versions/title-{title}.json"
                )
                if versions_resp.status_code != 200:
                    logger.error(f"Failed to retrieve versions for title {title}: {versions_resp.status_code}")
                    return {"error": f"Title {title} not found or rate limited",
                            "status_code": versions_resp.status_code}

                versions_json = versions_resp.json()
                versions = versions_json["content_versions"]
                self.cache[title] = versions
        logger.info(f"Cache populated with sections for {len(titles_json)} titles")

    async def get_titles(self):
        """Retrieve all titles from the eCFR API and store in a local cache"""
        if self.TITLES_KEY not in self.cache:
            titles_resp = await self.client.get(f"{urls.VRSN_URL}/titles.json")
            if titles_resp.status_code != 200:
                logger.error(f"Failed to retrieve titles: {titles_resp.status_code}")
                return {
                    "error": "Failed to retrieve titles",
                    "status_code": titles_resp.status_code,
                }
            titles = titles_resp.json()["titles"]
            self.cache[self.TITLES_KEY] = titles
            return titles
        else:
            logger.debug(f"Cache hit for titles {self.TITLES_KEY}")
            return self.cache[self.TITLES_KEY]

    async def get_title_sections(self, title):
        """Retrieve all sections from a title in the eCFR API and store in a local cache"""
        if title not in self.cache:
            versions_resp = await self.client.get(
                f"{urls.VRSN_URL}/versions/title-{title}.json"
            )
            if versions_resp.status_code != 200:
                logger.error(f"Failed to retrieve versions for title {title}: {versions_resp.status_code}")
                return {"error": f"Title {title} not found or rate limited",
                        "status_code": versions_resp.status_code}

            versions_json = versions_resp.json()
            versions = versions_json["content_versions"]
            self.cache[title] = versions
            return versions
        else:
            logger.debug(f"Cache hit for title {title}")
            return self.cache[title]

    def check_version_cache(self, title, versions):
        """"
        Check version cache for each section in the title and return False if it does not exist
        and needs to be retrieved.
        """
        section_tuples = []
        for version in versions:
            title = version["title"] if version["title"] else title
            part = version["part"] if version["part"] else "-"
            subpart = version["subpart"] if version["subpart"] else "-"
            identifier = version["identifier"] if version["identifier"] else "-"
            date = version["date"] if version["date"] else "-"
            removed = version["removed"] if version["removed"] else False
            version_key = f"{title}/{part}/{subpart}/{identifier}/{date}"
            section_date = version["date"]
            section_url = f"{urls.VRSN_URL}/full/{section_date}/title-{title}.xml"
            if version_key in self.cache:
                logger.info(f"Cache hit for {version_key}")
                section_tuples.append((version_key, section_url, False))
            logger.debug(f"Cache miss for {version_key}")
            section_tuples.append((version_key, section_url, True))
        return section_tuples

    async def get_title_words(self, title):
        """Tets word count for a single title"""
        key = f"title-counts/{title}"
        if key in self.cache:
            logger.info(f"Cache hit for {key}")
            content_xml = self.cache[key]
        else:
            logger.info(f"Cache miss for {key}")
            response = await self.client.get(f"{urls.VRSN_URL}/full/{TITLE_DATE}/title-{title}.xml")
            if response.status_code != 200:
                return {"error": f"Title {title} not found or rate limited",
                        "status_code": response.status_code}
            content_xml = response.text
            self.cache[key] = content_xml
        count_key = f"title-word-counts/{title}"
        if count_key in self.cache:
            logger.info(f"Cache hit for {count_key}")
            section_count = self.cache[count_key]
        else:
            section_count = word_count(content_xml)
            self.cache[count_key] = section_count
        logger.info(f"Title {title} has {section_count} words in total")
        return {"title": title, "word_count": section_count}

    async def get_section(self, section_tuple):
        """Retrieve a single section from the eCFR API. Intended to be used with asyncio.gather"""
        (key, url, retrieve) = section_tuple
        response = await self.client.get(url, timeout=30.00)
        if response.status_code != 200:
            logger.error(f"Failed to retrieve {url}: {response.status_code}")
            return None, None
        self.cache[key] = response.text
        logger.info(f"Put {key} in cache for {url}")
        return key, response

    async def get_title_word_count_by_sections(self, title):
        """
        Retrieve the word count for a title in the eCFR API, section by section.
        Caches both the HTTP XML response and the parsed word count from the XML for each section.
        """
        versions = await self.get_title_sections(title)
        title_word_count = 0
        section_tuples = self.check_version_cache(title, versions)

        section_responses = await asyncio.gather(*[self.get_section(sec_tup) for sec_tup in section_tuples])
        logger.info(f"Title {title} retrieving counts for {len(section_responses)} sections")
        for response in section_responses:
            key, response = response
            if response is None:
                continue
            content_xml = response.text
            self.cache[key] = content_xml

        for key, _url, _retrieve in section_tuples:
            content_xml = self.cache[key]
            word_count_key = f"word-counts/{key}"
            if word_count_key in self.cache:
                logger.info(f"Cache hit for {word_count_key}")
                section_count = self.cache[word_count_key]
            else:
                logger.info(f"Cache miss for {word_count_key}")
                section_count = word_count(content_xml)
                self.cache[word_count_key] = section_count
            title_word_count += section_count
            logger.info(f"Title {title} has {section_count} words in total")

        return title_word_count

    async def get_counts(self):
        titles = self.cache[self.TITLES_KEY]
        title_names = [item['number'] for item in titles]
        return {
            "title_count": len(title_names),
            "titles": title_names
        }


def word_count(xml_str: str) -> int:
    doc = etree.fromstring(xml_str.encode())
    text = " ".join(
        t.strip() for elem in doc.iter() for t in (elem.text, elem.tail) if t
    )
    return len(re.findall(r"\w+", text))
