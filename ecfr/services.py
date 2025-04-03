import asyncio
import json
import logging
import re
import shelve
from shelve import DbfilenameShelf

import httpx
from lxml import etree

from ecfr import urls
from main import active_tasks

logger = logging.getLogger("ecfr")

TITLE_DATE = "2025-03-31"


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
                    logger.error(
                        f"Failed to retrieve versions for title {title}: {versions_resp.status_code}"
                    )
                    return {
                        "error": f"Title {title} not found or rate limited",
                        "status_code": versions_resp.status_code,
                    }

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
                logger.error(
                    f"Failed to retrieve versions for title {title}: {versions_resp.status_code}"
                )
                return {
                    "error": f"Title {title} not found or rate limited",
                    "status_code": versions_resp.status_code,
                }

            versions_json = versions_resp.json()
            versions = versions_json["content_versions"]
            self.cache[title] = versions
            return versions
        else:
            logger.debug(f"Cache hit for title {title}")
            return self.cache[title]

    def check_version_cache(self, title, versions):
        """
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

    async def get_title_counts_cached(self, cached=True):
        """
        Retrieve word counts for all titles in the eCFR API.
        Gives a quick response with a sample response if the cache is empty.
        """
        first_run_cache_key = "first_run"
        counts_task_name = "counts_task"

        def get_title_counts_task():
            for task in active_tasks:
                if hasattr(task, '_task_name') and task._task_name == counts_task_name and not task.done():
                    return task
                return None

        if first_run_cache_key not in self.cache:
            logger.info("First run, populating cache, giving sample response")

            existing_task = get_title_counts_task()
            if existing_task:
                return json.loads(sample_title_counts)
            else:
                counts_task = asyncio.create_task(self.get_title_counts())
                counts_task._task_name = counts_task_name
                def first_run_done(t):
                    logger.info("First run done")
                    self.cache[first_run_cache_key] = True
                    active_tasks.discard(counts_task)
                counts_task.add_done_callback(first_run_done)
                active_tasks.add(counts_task)
            return json.loads(sample_title_counts)

        existing_task = get_title_counts_task()
        if existing_task:
            return json.loads(sample_title_counts)
        else:
            logger.info("Cache populated, retrieving title counts")
            counts_task = asyncio.create_task(self.get_title_counts(cached=cached))
            counts_task._task_name = counts_task_name
            active_tasks.add(counts_task)
            counts = []
            try:
                counts = await counts_task
            except asyncio.CancelledError:
                logger.info("Task started during shutdown")
                counts = []
            finally:
                return counts

    async def get_title_counts(self, cached=True):
        """Retrieve word counts for all titles in the eCFR API"""
        title_counts_key = "title-counts"
        if title_counts_key in self.cache and cached:
            logger.info(f"Cache hit for {title_counts_key}")
            return self.cache[title_counts_key]

        titles_json = await self.get_titles()
        titles = [item["number"] for item in titles_json]
        counts = [await self.get_title_words(title) for title in titles]
        self.cache[title_counts_key] = counts
        return counts

    async def get_title_words(self, title):
        """Gets word count for a single title"""
        key = f"title-counts/{title}"
        if key in self.cache:
            logger.info(f"Cache hit for {key}")
            content_xml = self.cache[key]
        else:
            logger.info(f"Cache miss for {key}")
            response = await self.client.get(
                f"{urls.VRSN_URL}/full/{TITLE_DATE}/title-{title}.xml"
            )
            if response.status_code != 200:
                return {
                    "title": title,
                    "word_count": 0,
                    "error": f"Title {title} not found or rate limited",
                    "status_code": response.status_code,
                }
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

        section_responses = await asyncio.gather(
            *[self.get_section(sec_tup) for sec_tup in section_tuples]
        )
        logger.info(
            f"Title {title} retrieving counts for {len(section_responses)} sections"
        )
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
        title_names = [item["number"] for item in titles]
        return {"title_count": len(title_names), "titles": title_names}


def word_count(xml_str: str) -> int:
    doc = etree.fromstring(xml_str.encode())
    text = " ".join(
        t.strip() for elem in doc.iter() for t in (elem.text, elem.tail) if t
    )
    return len(re.findall(r"\w+", text))

sample_title_counts = '[{"title": "1", "word_count": 69393}, {"title": "2", "word_count": 348252}, {"title": "3", "word_count": 4302}, {"title": "4", "word_count": 61581}, {"title": "5", "word_count": 1680516}, {"title": "6", "word_count": 265273}, {"title": "7", "word_count": 5881285}, {"title": "8", "word_count": 847269}, {"title": "9", "word_count": 1078540}, {"title": "10", "word_count": 2840892}, {"title": "11", "word_count": 250982}, {"title": "12", "word_count": 5894224}, {"title": "13", "word_count": 571469}, {"title": "14", "word_count": 2258606}, {"title": "15", "word_count": 1683376}, {"title": "16", "word_count": 977322}, {"title": "17", "word_count": 2537694}, {"title": "18", "word_count": 966321}, {"title": "19", "word_count": 1531979}, {"title": "20", "word_count": 2168518}, {"title": "21", "word_count": 2895151}, {"title": "22", "word_count": 975954}, {"title": "23", "word_count": 478352}, {"title": "24", "word_count": 1853440}, {"title": "25", "word_count": 855655}, {"title": "26", "word_count": 12643620}, {"title": "27", "word_count": 1073965}, {"title": "28", "word_count": 1424714}, {"title": "29", "word_count": 4115346}, {"title": "30", "word_count": 1437827}, {"title": "31", "word_count": 1445677}, {"title": "32", "word_count": 1895172}, {"title": "33", "word_count": 1597596}, {"title": "34", "word_count": 1300934}, {"title": "35", "word_count": 0, "error": "Title 35 not found or rate limited", "status_code": 404}, {"title": "36", "word_count": 1124535}, {"title": "37", "word_count": 672878}, {"title": "38", "word_count": 1341491}, {"title": "39", "word_count": 330609}, {"title": "40", "word_count": 17827071}, {"title": "41", "word_count": 766621}, {"title": "42", "word_count": 3282461}, {"title": "43", "word_count": 1196652}, {"title": "44", "word_count": 344404}, {"title": "45", "word_count": 2205816}, {"title": "46", "word_count": 2048160}, {"title": "47", "word_count": 2480965}, {"title": "48", "word_count": 2799489}, {"title": "49", "word_count": 4288192}, {"title": "50", "word_count": 3940123}]'