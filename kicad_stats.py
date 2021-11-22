#!/usr/bin/env python3

import logging
import os
import re
import requests
from dotenv import load_dotenv
from urllib.parse import urlparse

# create console handler and set level to debug
logging_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s;%(levelname)s;%(message)s", "%Y-%m-%d %H:%M:%S")
logging_handler.setFormatter(formatter)

# add ch to logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.addHandler(logging_handler)

USER_AGENT = 'https://github.com/pointhi/kicad-package-repository-stats/'
DEFAULT_HEADERS = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}

REPOSITORY_JSON = 'https://repository.kicad.org/repository.json'

GITHUB_DOWNLOAD_URL = re.compile(r"^/(?P<username>[^/]+)/(?P<repository>[^/]+)/releases/download/(?P<tag>[^/]+)/(?P<filename>.*)$")
GITHUB_RELEASE_API_ENDPOINT = "https://api.github.com/repos/{username}/{repository}/releases/tags/{tag}"


def get_packages_json():
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    logger.debug('Download "%s"', REPOSITORY_JSON)
    repository_json = session.get(REPOSITORY_JSON)
    if repository_json.status_code >= 400:
        logger.error('"%s" returned status code %d', REPOSITORY_JSON, repository_json.status_code)
        exit(1)
    packages_data = repository_json.json()

    packages_json_url = packages_data.get('packages', {}).get('url')
    if not packages_json_url:
        logger.error('No packages.json url found')
        exit(1)
    logger.debug('Download "%s"', packages_json_url)
    packages_json = session.get(packages_json_url)
    if packages_json.status_code >= 400:
        logger.error('"%s" returned status code %d', packages_json_url, packages_json.status_code)
        exit(1)

    return packages_json.json()


def get_download_count(session, url):
    url_parts = urlparse(url)
    if not url_parts:
        return None

    # we only support Github for now
    if url_parts.hostname != "github.com":
        return None

    github_download_match = GITHUB_DOWNLOAD_URL.match(url_parts.path)
    if not github_download_match:
        return None

    github_release_api_url = GITHUB_RELEASE_API_ENDPOINT.format(**github_download_match.groupdict())
    logger.debug('Download "%s"', github_release_api_url)
    release_json = session.get(github_release_api_url)
    if release_json.status_code >= 400:
        logger.error('"%s" returned status code %d', release_json, packages_json.status_code)
        return None

    release_data = release_json.json()
    for asset in release_data.get('assets', []):
        browser_download_url = asset.get('browser_download_url')
        asset_download_match = GITHUB_DOWNLOAD_URL.match(urlparse(browser_download_url).path)
        if not asset_download_match:
            continue

        if asset_download_match.groupdict() == github_download_match.groupdict():
            return asset.get('download_count')

    return None


if __name__ == '__main__':
    load_dotenv()
    GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')

    found_downloads = {}

    packages_json = get_packages_json()
    for package in packages_json.get('packages', []):
        name = package.get('name')
        identifier = package.get('identifier')
        logger.debug('Analyze "%s" - "%s"', name, identifier)
        for release in package.get('versions', []):
            version = release.get('version')
            download_url = release.get('download_url')
            if not download_url:
                continue
            logger.debug('Version "%s" can be downloaded from "%s"', version, download_url)
            found_downloads[download_url] = {"identifier": identifier, "version": version}

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    if GITHUB_TOKEN:
        session.headers.update({'authorization': f'Bearer {GITHUB_TOKEN}'})

    for url, info in found_downloads.items():
        download_count = get_download_count(session, url)
        if download_count is None:
            logger.info('Package "%s" has no download statistics available', url)
        else:
            logger.info('Package "%s" was downloaded %d times', url, download_count)
