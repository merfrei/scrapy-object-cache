"""
Scrapy Object Cache Middlewares.

It contains a Spider Middleware and a Downloader Middleware.

You should setup them both in your settings.py.

It makes use of Mokeskin API, please refer to this for more
information about the API.
"""

import json
import hashlib
import requests
from urllib.parse import urljoin
from scrapy.http import HtmlResponse
from scrapy.utils.request import request_fingerprint


TAG_NAME = 'cm_spiders'  # Default Tag Name for Mokeskin stored data
MOKESKIN_TTL = 60 * 60 * 6  # Default TTL: 6 hours


def get_spider_request_key(spider, request):
    request_key = request_fingerprint(request)
    request_key_callback = None
    if hasattr(spider, 'httpcache_get_request_key'):
        if callable(spider.httpcache_get_request_key):
            request_key_callback = spider.httpcache_get_request_key
    if hasattr(spider, 'get_request_key'):
        if callable(spider.get_request_key):
            request_key_callback = spider.get_request_key
    if request_key_callback is not None:
        key = request_key_callback(request)
        if key is not None:
            request_key = key
    spider_key = hashlib.md5(spider.name).hexdigest()
    return '{}:{}'.format(spider_key, request_key)


def get_api_url(url, qry):
    return (url + '?{}'.format(qry))


def get_spider_request_ttl(spider, request):
    ttl = request.meta.get('MOKESKIN_TTL')
    if ttl is None:
        ttl = spider.settings.get('MOKESKIN_TTL', MOKESKIN_TTL)
    return ttl


class ScrapyObjectSpiderMiddleware(object):

    def _mokeskin_url(self, spider, item=None):
        mk_host = spider.settings.get('MOKESKIN_HOST', None)
        if mk_host is None:
            raise ScrapyObjectSpiderMiddlewareError(
                'ERROR: You must setup MOKESKIN_HOST in settings.py')
        mk_api_key = spider.settings.get('MOKESKIN_API_KEY', None)
        if mk_api_key is None:
            raise ScrapyObjectSpiderMiddlewareError(
                'ERROR: You must setup MOKESKIN_API_KEY in settings.py')
        mk_tag = spider.settings.get('MOKESKIN_TAG_NAME', TAG_NAME)
        mk_route = 'items'
        mk_query = 'tag={}&api_key={}'.format(mk_tag, mk_api_key)
        url = urljoin(mk_host, mk_route)
        if item is not None:
            url = url + '/' + item
        return get_api_url(url, mk_query)

    def _mokeskin_get_data(self, spider, request):
        """Get data by TAG_NAME + key from Mokeskin

        @type spider: Spider
        @param spider: the spider which is running the current crawl

        @type request: Request
        @param request: the current request
        """
        mk_key = get_spider_request_key(spider, request)
        mk_url = self._mokeskin_url(spider, item=mk_key)
        resp = requests.get(mk_url)
        stat_code = resp.status_code
        if stat_code != 200:
            spider.log('Spider Object Cache (GET): ERROR - No 200 response '
                       'URL: {}, CODE: {}'.format(mk_url, stat_code))
            return None
        return resp.json()['data']

    def _mokeskin_post_data(self, spider, request, data):
        """Post data to Mokeskin using TAG_NAME + key

        @type spider: Spider
        @param spider: the spider which is running the current crawl

        @type request: Request
        @param request: the current request

        @type data: JSON serializable object
        @param data: the data to store in Mokeskin
        """
        mk_url = self._mokeskin_url(spider)
        full_data = {}  # It includes the data, the key and also the expiration (ttl)
        full_data['key'] = get_spider_request_key(spider, request)
        full_data['data'] = data
        full_data['exp'] = get_spider_request_ttl(spider, request)
        resp = requests.post(mk_url, json=full_data)
        stat_code = resp.status_code
        if stat_code != 201:
            spider.log('Spider Object Cache (POST): ERROR - No 201 response '
                       'URL: {}, CODE: {}'.format(mk_url, stat_code))

    def _serialize_request(self, request):
        pass

    def _deserialize_request(self, data):
        pass

    def _serialize_item(self, item):
        pass

    def _deserialize_item(self, data):
        pass

    def _deserialize_mokeskin_response(self, response):
        pass

    def process_spider_output(response, result, spider):
        """Store Requests and Items into Mokeskin"""
        pass

    def process_spider_output(response, result, spider):
        """Return Requests or Items from Mokeskin"""
        pass


class ScrapyObjectDownloadMiddleware(object):

    def _is_enabled(self, request, spider):
        is_enabled = request.meta.get('cache_object_enabled')
        if is_enabled is None:
            is_enabled = getattr(spider, 'cache_object_enabled', False)
        return is_enabled

    def process_request(self, request, spider):
        use_cache = self._is_enabled(request, spider)
        if use_cache:
            mokeskin_host = spider.settings.get('MOKESKIN_HOST')
            spider_key = get_spider_key(spider)
