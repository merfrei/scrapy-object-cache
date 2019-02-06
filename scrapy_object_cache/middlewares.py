"""
Scrapy Object Cache Middlewares.

It contains a Spider Middleware and a Downloader Middleware.
You should setup them both in your settings.py.

It makes use of Mokeskin API, please refer to this for more
information about the API.
"""

import hashlib
from scrapy_object_cache.mokeskin import MokeskinAPI
from scrapy_object_cache.mokeskin import MokeskinAPIError
from scrapy import Request
from scrapy import Item
from scrapy.exceptions import NotConfigured
from scrapy.utils.request import request_fingerprint


TAG_NAME = 'scrapy_spiders'  # Default Tag Name for Mokeskin stored data
MOKESKIN_TTL = 60 * 60 * 6  # Default TTL: 6 hours


def check_if_is_enabled(self, request, spider):
    is_enabled = request.meta.get('cache_object_enabled')
    if is_enabled is None:
        is_enabled = getattr(spider, 'cache_object_enabled', False)
    return is_enabled


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


class ScrapyObjectSpiderMiddleware(object):

    @classmethod
    def from_crawler(cls, crawler):
        mk_host = crawler.settings.get('MOKESKIN_HOST', None)
        if mk_host is None:
            raise NotConfigured(
                'ERROR: You must setup MOKESKIN_HOST in settings.py')

        mk_api_key = crawler.settings.get('MOKESKIN_API_KEY', None)
        if mk_api_key is None:
            raise NotConfigured(
                'ERROR: You must setup MOKESKIN_API_KEY in settings.py')

        mk_ttl = crawler.settings.get('MOKESKIN_TTL', MOKESKIN_TTL)

        mk_tag_name = crawler.settings.get('MOKESKIN_TAG_NAME', TAG_NAME)

        return cls(mk_host, mk_api_key, mk_tag_name, mk_ttl)

    def __init__(self, mk_host, mk_api_key, mk_tag_name, mk_ttl):
        self.mk_api = MokeskinAPI(host=mk_host,
                                  api_key=mk_api_key,
                                  tag_name=mk_tag_name,
                                  ttl=mk_ttl)

    def get_request_ttl(self, request):
        return request.meta.get('MOKESKIN_TTL', None)

    def get_spider_request_key(self, spider, request):
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

    def _serialize_request(self, request):
        request_dt = {
            'url': request.url,
            'method': request.method,
            'body': request.body,
            'headers': request.headers,
            'meta': request.meta,
            'dont_filter': request.dont_filter,
            'cookies': request.cookies,
        }
        if request.callback is not None:
            request_dt['callback'] = request.callback.__name__
        if request.errback is not None:
            request_dt['errback'] = request.errback.__name__
        return request_dt

    def _serialize_item(self, item):
        return dict(item)

    def get_data(self, spider, request):
        """Get data by TAG_NAME + key from Mokeskin

        @type spider: Spider
        @param spider: the spider which is running the current crawl

        @type request: Request
        @param request: the current request
        """
        mk_key = get_spider_request_key(spider, request)
        try:
            data = self.mk_api.get(mk_key)
        except MokeskinAPIError as e:
            spider.log('Spider Object Cache (Mokeskin ERROR): {!r}'.format(e))
            return None
        return data

    def post_data(self, spider, request, data, ttl=None):
        """Post data to Mokeskin using TAG_NAME + key

        @type spider: Spider
        @param spider: the spider which is running the current crawl

        @type request: Request
        @param request: the current request

        @type data: JSON serializable object
        @param data: the data to store in Mokeskin

        @type ttl: integer
        @param ttl: the expiration time in seconds (optional)
        """
        mk_key = get_spider_request_key(spider, request)
        try:
            self.mk_api.post(mk_key, data, ttl)
        except MokeskinAPIError as e:
            spider.log('Spider Object Cache (Mokeskin ERROR): {!r}'.format(e))
        else:
            spider.log('Spider Object Cache: data stored ({})'.format(mk_key))

    def process_spider_output(self, response, result, spider):
        """Store Requests and Items into Mokeskin"""
        use_cache = check_if_is_enabled(response.request, spider)
        if use_cache:
            data = []
            for obj in result:
                if isinstance(obj, Request):
                    data.append(self._serialize_request(obj))
                elif isinstance(obj, [dict, Item]):
                    data.append(self._serialize_item(obj))
                else:
                    spider.log('Spider Object Cache (Spider Output): WARNING - '
                               'unknown object => {!r}'.format(obj))


class ScrapyObjectDownloaderMiddleware(object):

    def _deserialize_request(self, data, spider):
        req = Request(url=data['url'],
                      method=data['method'],
                      body=data['body'].encode('utf-8'),
                      headers=data['headers'],
                      meta=data['meta'],
                      dont_filter=data['dont_filter'],
                      cookies=data['cookies'])
        callback = data.get('callback')
        if callback is not None and hasattr(spider, callback):
            spider_pm = getattr(spider, callback)
            if callable(spider_pm):
                req.callback = spider_pm
        errback = data.get('errback')
        if errback is not None and hasattr(spider, errback):
            spider_em = getattr(spider, errback)
            if callable(spider_em):
                req.errback = spider_em
        return req

    def _deserialize_item(self, data):
        pass

    def _get_parse_mokeskin_cache(self, response):
        pass

    def process_request(self, request, spider):
        use_cache = check_if_is_enabled(request, spider)
        if use_cache:
            mokeskin_host = spider.settings.get('MOKESKIN_HOST')
            spider_key = get_spider_request_key(spider, request)
