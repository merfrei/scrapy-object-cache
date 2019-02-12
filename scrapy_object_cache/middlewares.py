"""
Scrapy Object Cache Middlewares.

It contains a Spider Middleware and a Downloader Middleware.
You should setup them both in your settings.py.

It makes use of Mokeskin API, please refer to this for more
information about the API.
"""

import hashlib
import importlib
from scrapy_object_cache.mokeskin import MokeskinAPI
from scrapy_object_cache.mokeskin import MokeskinAPIError
from scrapy import Request
from scrapy import Item
from scrapy.exceptions import NotConfigured
from scrapy.utils.request import request_fingerprint


TAG_NAME = 'scrapy_spiders'  # Default Tag Name for Mokeskin stored data
MOKESKIN_TTL = 60 * 60 * 6  # Default TTL: 6 hours


def check_if_is_enabled(request, spider):
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


def get_mk_api_from_crawler(crawler):
    mk_host = crawler.settings.get('MOKESKIN_HOST', None)
    if mk_host is None:
        raise NotConfigured(
            'ERROR: You must setup MOKESKIN_HOST in settings.py')
    mk_api_key = crawler.settings.get('MOKESKIN_API_KEY', None)
    if mk_api_key is None:
        raise NotConfigured(
            'ERROR: You must setup MOKESKIN_API_KEY in settings.py')
    mk_tag_name = crawler.settings.get('MOKESKIN_TAG_NAME', TAG_NAME)
    mk_ttl = crawler.settings.get('MOKESKIN_TTL', MOKESKIN_TTL)
    return MokeskinAPI(host=mk_host,
                       api_key=mk_api_key,
                       tag_name=mk_tag_name,
                       ttl=mk_ttl)


class ScrapyObjectSpiderMiddleware(object):

    @classmethod
    def from_crawler(cls, crawler):
        mk_api = get_mk_api_from_crawler(crawler)
        return cls(mk_api)

    def __init__(self, mk_api):
        self.mk_api = mk_api

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
        """Get data from Mokeskin for spider + request

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
        """Post data to Mokeskin for spider + request

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

    def exists_data(self, spider, request):
        """Check if any data exists in Mokeskin for spider + request

        @type spider: Spider
        @param spider: the spider which is running the current crawl

        @type request: Request
        @param request: the current request
        """
        mk_key = get_spider_request_key(spider, request)
        try:
            result = self.mk_api.exists(mk_key)
        except MokeskinAPIError as e:
            spider.log('Spider Object Cache (Mokeskin ERROR): {!r}'.format(e))
            return None
        return result

    def process_spider_output(self, response, result, spider):
        """Store Requests and Items into Mokeskin"""
        use_cache = check_if_is_enabled(response.request, spider)
        if use_cache:
            result = list(result)
            key_exists = self.exists_data(spider, response.request)
            # Check if there is some cached data existing before
            if not key_exists:
                data = []
                for obj in result:
                    obj_data = {'_type': '', '_data': None}
                    if isinstance(obj, Request):
                        obj_data['_type'] = 'request'
                        obj_data['_data'] = self._serialize_request(obj)
                    elif isinstance(obj, [dict, Item]):
                        obj_data['_type'] = 'item'
                        obj_data['_data'] = self._serialize_item(obj)
                    else:
                        spider.log('Spider Object Cache (Spider Output): WARNING - '
                                   'unknown object => {!r}'.format(obj))
                        continue
                    data.append(obj_data)
                req_ttl = self.get_request_ttl(response.request)
                self.post_data(spider, response.request, data, req_ttl)
        return result


class ScrapyObjectDownloaderMiddleware(object):

    def __init__(self, mk_api, item_cls, loader_cls, loader_conf, spider):
        """ScrapyObjectDownloaderMiddleware

        @type item_cls: scrapy.Item
        @param item_cls: Item to use at the item deserializer

        @type loader_cls: scrapy.ItemLoader
        @param loader_cls: ItemLoader to use at the item deserializer

        @type loader_conf: dict
        @param loader_conf: type configuration for some fields (field => type)
        """
        self.mk_api = mk_api
        self.item_cls = item_cls
        self.loader_cls = loader_cls
        self.loader_conf = loader_conf
        self.spider = spider

    @classmethod
    def from_crawler(cls, crawler):
        mk_api = get_mk_api_from_crawler(crawler)

        item_path = crawler.settings.get('OBJECT_CACHE_ITEM', None)
        if item_path is None:
            raise NotConfigured(
                'ERROR: You must setup OBJECT_CACHE_ITEM in settings.py')

        loader_path = crawler.settings.get('OBJECT_CACHE_ITEM_LOADER', None)
        if loader_path is None:
            raise NotConfigured(
                'ERROR: You must setup OBJECT_CACHE_ITEM_LOADER in settings.py')

        loader_conf = crawler.settings.get('OBJECT_CACHE_ITEM_LOADER_CONFIG', None)
        if loader_conf is None:
            raise NotConfigured(
                'ERROR: You must setup OBJECT_CACHE_ITEM_LOADER_CONFIG in settings.py')

        item_cls = cls.get_attr_from_path(item_path)
        loader_cls = cls.get_attr_from_path(loader_path)

        return cls(mk_api, item_cls, loader_cls, loader_conf, crawler.spider)

    @staticmethod
    def get_attr_from_path(path):
        mod_path = '.'.join(path.split('.')[:-1])
        attr_str = path.split('.')[-1]
        mod = importlib.import_module(mod_path)
        return getattr(mod, attr_str)

    def _log(self, msg):
        if hasattr(self.spider, 'log'):
            if callable(self.spider.log):
                self.spider.log(msg)

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

    def _deserialize_item(self, data, response):
        loader = self.loader(item=self.item_cls(), response=response)
        for k, v in data.items():
            fld = k
            val = v
            if k in self.loader_conf:
                val = self.loader_conf[k](v)
            loader.load_value(fld, val)
        return loader.load_item()

    def _dummy_request(self, mk_key):
        return Request('file:///etc/hosts',
                       meta={'mk_key': mk_key,
                             'keep_session': True},
                       callback=self.get_and_parse_mokeskin_cache,
                       dont_filter=True)

    def exists_data(self, mk_key):
        """
        @type mk_key: string
        @param mk_key: Mokeskin key
        """
        try:
            result = self.mk_api.exists(mk_key)
        except MokeskinAPIError as e:
            self._log('Spider Object Cache (Mokeskin ERROR): {!r}'.format(e))
            return None
        return result

    def get_data(self, mk_key):
        """
        @type mk_key: string
        @param mk_key: Mokeskin key
        """
        try:
            data = self.mk_api.get(mk_key)
        except MokeskinAPIError as e:
            self._log('Spider Object Cache (Mokeskin ERROR): {!r}'.format(e))
            return None
        return data

    def get_and_parse_mokeskin_cache(self, response):
        mk_key = response.meta['mk_key']
        data = self.get_data(mk_key)
        for mk_obj in data:
            obj_type = mk_obj['_type']
            if obj_type == 'request':
                yield self._deserialize_request(
                    data=mk_obj['data'],
                    spider=self.spider)
            elif obj_type == 'item':
                yield self._deserialize_item(
                    data=mk_obj['data'],
                    response=response)

    def process_request(self, request, spider):
        """It check for stored objects in Mokeskin.
        In case there is something it will return a new dummy request
        where it'll process all the stored objects"""
        use_cache = check_if_is_enabled(request, spider)
        if use_cache:
            mk_key = get_spider_request_key(spider, request)
            if self.exists_data(mk_key):
                return self._dummy_request(mk_key)
