import requests
try:
    from urllib.parse import urljoin
except ImportError:
    from urlparse import urljoin


def get_api_url(url, qry):
    return (url + '?{}'.format(qry))



class MokeskinAPIError(Exception):
    pass


class MokeskinAPI(object):

    def __init__(self, host, api_key, tag_name, ttl=None):
        self.host = host
        self.api_key = api_key
        self.tag_name = tag_name
        self.ttl = ttl

    def _mokeskin_url(self, key=None, exists=False):
        mk_route = '/items'
        if exists:
            mk_route = '/exists'
        mk_query = 'tag={}&api_key={}'.format(self.tag_name, self.api_key)
        url = urljoin(self.host, mk_route)
        if key is not None:
            url = url + '/' + key
        return get_api_url(url, mk_query)

    def get(self, key):
        mk_url = self._mokeskin_url(key=key)
        resp = requests.get(mk_url)
        stat_code = resp.status_code
        if stat_code == 404:
            return None  # No data found for this key
        elif stat_code != 200:
            raise MokeskinAPIError('[GET] ERROR - No 200 response '
                                   'URL: {}, CODE: {}'.format(mk_url, stat_code))
        return resp.json()['data']['data']

    def post(self, key, data, ttl=None):
        mk_url = self._mokeskin_url()
        full_data = {}  # It includes the data, the key and also the expiration (ttl)
        full_data['key'] = key
        full_data['data'] = data
        if ttl is not None:
            full_data['exp'] = int(ttl)
        elif self.ttl is not None:
            full_data['exp'] = int(self.ttl)
        resp = requests.post(mk_url, json=full_data)
        stat_code = resp.status_code
        if stat_code != 201:
            raise MokeskinAPIError('[POST] ERROR - No 201 response '
                                   'URL: {}, CODE: {}'.format(mk_url, stat_code))

    def exists(self, key):
        mk_url = self._mokeskin_url(key=key, exists=True)
        resp = requests.get(mk_url)
        stat_code = resp.status_code
        if stat_code == 404:
            return False
        elif stat_code != 200:
            raise MokeskinAPIError('[EXISTS] ERROR - No 200 response '
                                   'URL: {}, CODE: {}'.format(mk_url, stat_code))
        return True
