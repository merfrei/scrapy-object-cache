Scrapy Object Cache
===================

Cache to store objects in Scrapy Framework, using an API to store objects (**Mokeskin API**)

It stores Requests and Items.

**IMPORTANT: You need to have Mokeskin API installed and running before start using Scrapy Object Cache**

## How it works and How to use

It includes two middlewares. An **Spider Middleware** (https://doc.scrapy.org/en/latest/topics/spider-middleware.html) and a **Downloader Middleware** (https://doc.scrapy.org/en/latest/topics/downloader-middleware.html)

The **Spider Middleware** stores the Items and the Requests after the parse method "returned" them.

The **Downloader Middleware** works before the request is made, check if there is some cached data and it returns this data if there is something (in simple...). Actually, internally, it generates a new "dummy request" and derivates the logic to an internal parse method which will collect all the cached objects, deserialize them and yield the results.

### Install

Using PIP

**pip install -e git+ssh://git@bitbucket.org/competitormonitor/scrapy-object-cache.git#egg=scrapy-object-cache**

### Settings

To make use of this you should add the two middlewares to the Scrapy settings file

```python
SPIDER_MIDDLEWARES['scrapy_object_cache.middlewares.ScrapyObjectSpiderMiddleware'] = 543
DOWNLOADER_MIDDLEWARES['scrapy_object_cache.middlewares.ScrapyObjectDownloaderMiddleware'] = 901
```

Also you should add some config. Specify the main Item class, the Loader to use for the items.

And also some config for the Items (a dict with the field and the type when need it).

```python
OBJECT_CACHE_ITEM = 'product_spiders.items.Product'
OBJECT_CACHE_ITEM_LOADER = 'product_spiders.items.ProductLoader'
OBJECT_CACHE_ITEM_LOADER_CONFIG = {'stock': int}
```

At last, you need to add the Mokeskin config:

```python
MOKESKIN_HOST = 'http://127.0.0.1:5678'  # Please put a valid host URL
MOKESKIN_API_KEY = '1234'  # The Mokeskin API api key
MOKESKIN_TAG_NAME = 'cm-spiders-'  # It's a prefix to be added to the object key
MOKESKIN_TTL = 60 * 60 * 6  # The TTL time. In seconds. After this time, the object will be removed from cache
```

### Use

The basic thing is to add the following as argument of the spider:

```python
class MySpider(Spider):
    name = 'myspider.com'
    ...
    cache_object_enabled = True
```

### Tricks and Recommended configs

- By default this will use the Request fingerprint to save the objects. This does not always work as we want, so I recommend using a cutom function to generate the key from the request.

We can do this in two ways. The middleware accepts two different methods in the spider: *httpcache_get_request_key* (for compatibility with current HTTP Cache middleware) and *get_request_key*.

For example, the following spider is using Pyppeteer API, and it will use the current URL's MD5 hash:

```python
    def httpcache_get_request_key(self, request):
        if 'wayfair.com' in request.url:
            page_url = request.url
        else:
            page_url = request.meta.get('pyppeteer_origin_url', request.url)
        return hashlib.md5(page_url).hexdigest()
```

- The cache can be completely deactivated for a selected request, paying attention that using the cache for all requests can cause issues. **It is recommended to analyze in advance what should be cached and what shouldn't**

To do that just set `cache_object_enabled` to `False` in the Request meta dictionary.

```python
    def parse_method(self, response):
        ...
        yield Request(url, meta={'cache_object_enabled': False})
```

- We can also disable the cache for a specific **Request** object. Recommended in the Requests that are retries.

```python
    def parse_method(self, response):
        ...
        yield Request(url, meta={'dont_cache_object': True})
```

- You can set the TTL (expiration time) to use per spider. It's set as an argument in the spider, **mokeskin_ttl**.

```python
class MySpider(Spider):
    name = 'myspider.com'
    ...
    cache_object_enabled = True
    mokeskin_ttl = 60 * 60 * 20  # 20 hs
```

You can also set it up per Request.

```python
    def parse_method(self, response):
        ...
        yield Request(url, meta={'mokeskin_ttl': 43200})
```
