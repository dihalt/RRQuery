import time
import logging
import sys
import urllib.request
import json
import RRQuertyCore
import requests
import time
import random

from dataclasses import dataclass
from urllib.parse import urlencode, quote_plus

def _get_body_for_logging(body: bytes) -> str:
    if body:
        return (b' BODY: ' + body).decode('utf-8')
    else:
        return ''

def _get_duration_for_logging(duration: str) -> str:
    if duration is not None:
        return ' {0:.6f}s'.format(duration)
    else:
        return ''


logger = logging.getLogger(__name__)

class HTTPClientConst:
    REFERCODE = random.randint(1, 10000)
    CHROMEVER = random.randint(1, 10000)

ClientConst = HTTPClientConst()

class HTTPClient:
    GET_HTTP_METHOD = 'GET'
    POST_HTTP_METHOD = 'POST'
    PATCH_HTTP_METHOD = 'PATCH'
    PUT_HTTP_METHOD = 'PUT'

    BODY_LESS_METHODS = [GET_HTTP_METHOD]
    LOG_REQUEST_TEMPLATE = '%(method)s %(url)s%(request_body)s%(duration)s'
    LOG_RESPONSE_TEMPLATE = (LOG_REQUEST_TEMPLATE +
                             ' - HTTP %(status_code)s%(response_body)s%(duration)s')
    AGENTSTR = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.{ver} Safari/537.36'
    REFER = 'https://pkk{code}.rosreestr.ru/'



    def __init__(self, timeout=3, keep_alive=False, default_headers=None):


        self.timeout = timeout
        self.keep_alive = keep_alive
        self.default_headers = default_headers or {
            'referer':self.REFER.format(code=ClientConst.REFERCODE),
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'accept-encoding': 'gzip, deflate, br',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'sec-fetch-mode' : 'cors',
            'sec-fetch-site' : 'same-origin',
            'user-agent':  self.AGENTSTR.format(ver=ClientConst.CHROMEVER)}
        self._session = None

    def ChangeAgent(self):
        ClientConst.CHROMEVER = random.randint(1, 10000)
        ClientConst.REFERCODE = random.randint(1, 10000)
        self.default_headers['user-agent'] = self.AGENTSTR.format(ver=ClientConst.CHROMEVER)
        self.default_headers['referer'] = self.REFER.format(code=ClientConst.REFERCODE)

    def _log_request(self, method, url, body, duration=None, log_method=logger.info):
        message_params = {
            'method': method, 'url': url, 'request_body': _get_body_for_logging(body),
            'duration': _get_duration_for_logging(duration)}
        log_method(self.LOG_REQUEST_TEMPLATE, message_params)

    def _log_response(self, response, duration, log_method=logger.info):
        message_params = {
            'method': response.request.method,
            'url': response.request.url,
            'request_body': _get_body_for_logging(response.request.body),
            'status_code': response.status_code,
            'response_body': _get_body_for_logging(response.content),
            'duration': _get_duration_for_logging(duration)}
        log_method(self.LOG_RESPONSE_TEMPLATE, message_params)

    def _make_request(self, method, url, **kwargs) -> requests.Response:
        kwargs.setdefault('timeout', self.timeout)
        session = self.session
        timeout = kwargs.pop('timeout', self.timeout)

        headers = self.default_headers.copy()
        headers.update(kwargs.pop('headers', {}))

        request = requests.Request(method, url, headers=headers, **kwargs)
        prepared_request = request.prepare()
        self._log_request(method, url, prepared_request.body)
        start_time = time.time()
        try:
            response = session.send(prepared_request, timeout=timeout)
            duration = time.time() - start_time
            if response.status_code >= 400:
                log_method = logging.error
            else:
                log_method = logging.debug

            self._log_response(response, duration=duration, log_method=log_method)
            return response
        except requests.exceptions.RequestException as e:
            duration = time.time() - start_time
            if e.response:
                self._log_response(e.response, duration=duration, log_method=logging.error)
            else:
                self._log_request(method, url, prepared_request.body, log_method=logging.exception)
            raise
        finally:
            if not self.keep_alive:
                session.close()

    @property
    def session(self) -> requests.Session:
        if self.keep_alive:
            if not self._session:
                self._session = requests.Session()
            return self._session
        else:
            return requests.Session()

    def get(self, url, params=None, **kwargs) -> requests.Response:
        if params:
            url_with_query_params = url + '?' + urlencode(params)
        else:
            url_with_query_params = url

        return self._make_request(self.GET_HTTP_METHOD, url_with_query_params, **kwargs)

    def post(self, url, **kwargs) -> requests.Response:
        return self._make_request(self.POST_HTTP_METHOD, url, **kwargs)

    def patch(self, url, **kwargs) -> requests.Response:
        return self._make_request(self.PATCH_HTTP_METHOD, url, **kwargs)

    def put(self, url, **kwargs) -> requests.Response:
        return self._make_request(self.PUT_HTTP_METHOD, url, **kwargs)


@dataclass
class AddressWrapper:

    street_name: str
    house_number: str
    macro_region_id: str = ''
    region_id: str = ''
    house_building: str = ''
    house_structure: str = ''
    apartment: str = ''
    macro_region_type: str = ''

    region_name: str = ''
    macro_region_name: str = ''

    def __post_init__(self):
        is_region_filled = self.region_name or self.region_id
        is_macro_region_filled = self.macro_region_name or self.macro_region_id
        if not (is_macro_region_filled and is_region_filled):
            raise ValueError('You have to provide region and macro region values')


class RosreestrAPIClient:

    BASE_URL = 'http://rosreestr.ru/api/online'
    MACRO_REGIONS_URL = f'{BASE_URL}/macro_regions/'
    REGIONS_URL = f'{BASE_URL}/regions/' + '{}/'
    REGION_TYPES_URL = f'{BASE_URL}/region_types/' + '{}/'
    SEARCH_OBJECTS_BY_RIGHT_URL = f'{BASE_URL}/right/' + '{}/{}/'
    SEARCH_OBJECTS_BY_ADDRESS_URL = (
        f'{BASE_URL}/address/fir_objects/'
        + '?macroRegionId={macro_region_id}&regionId={region_id}'
        + '&street={street_name}&house={house_number}&building={house_building}'
        + '&structure={house_structure}&apartment={apartment}')
    SEARCH_DETAILED_OBJECT_BY_ID = f'{BASE_URL}/fir_object/' + '{}/'

    REPUBLIC = 'республика'

    def __init__(self, timeout=5, keep_alive=False):
        self._http_client = HTTPClient(timeout=timeout, keep_alive=keep_alive)
        self._macro_regions = None
        self._macro_regions_to_regions = None

    def _get_response_body(self, response: requests.Response):
        status_code = response.status_code
        if status_code >= 400:
            response.raise_for_status()
        elif status_code == 204:
            logger.info('There was an empty response body')
            return ''
        else:
            return response.json()

    def _get_macro_region_id(self, macro_region_name: str):
        for macro_region in self.macro_regions:
            if macro_region['name'].lower() == macro_region_name.lower():
                return macro_region['id']
        raise ValueError(
            f'There was not found suitable macro region '
            f'for macro region name - `{macro_region_name}`')

    def _get_region_id(self, region_name: str, macro_region_name: str) -> int:
        macro_region_id = self._get_macro_region_id(macro_region_name)
        for region in self.macro_regions_to_regions[macro_region_id]:
            if region['name'].lower() == region_name.lower():
                return region['id']
        raise ValueError(
            f'There was not found suitable region_id for '
            f'region name - `{region_name}` and macro region '
            f'name - `{macro_region_name}`')

    @property
    def macro_regions(self):
        if not self._macro_regions:
            self._macro_regions = self._http_client.get(self.MACRO_REGIONS_URL).json()
            logger.info('Macro regions were downloaded')
        return self._macro_regions

    @property
    def macro_regions_to_regions(self):
        if not self._macro_regions_to_regions:
            self._macro_regions_to_regions = {}
            for macro_region in self.macro_regions:
                response = self._http_client.get(
                    self.REGIONS_URL.format(macro_region['id']))
                self._macro_regions_to_regions[
                    macro_region['id']] = response.json()
            logger.info('Regions were downloaded')
        return self._macro_regions_to_regions

    def get_region_types(self, region_id: str):
        response = self._http_client.get(self.REGION_TYPES_URL.format(region_id))
        return self._get_response_body(response)

    def get_objects_by_right(self, region_number: str, right_number: str):
        url = self.SEARCH_OBJECTS_BY_RIGHT_URL.format(region_number, quote_plus(right_number))
        return self._get_response_body(self._http_client.get(url))

    def get_objects_by_address(self, address_wrapper: AddressWrapper):
        macro_region_id = address_wrapper.macro_region_id
        if not address_wrapper.macro_region_id:
            macro_region_name = address_wrapper.macro_region_name.lower()
            if macro_region_name.endswith('ая'):
                macro_region_name = macro_region_name + ' область'
            elif macro_region_name.endswith('ий'):
                macro_region_name = macro_region_name + ' край'
            elif address_wrapper.macro_region_type.lower() == self.REPUBLIC:
                macro_region_name = f'{self.REPUBLIC} {macro_region_name}'
            macro_region_id = self._get_macro_region_id(macro_region_name)

        region_id = address_wrapper.region_id
        if not region_id:
            region_id = self._get_region_id(
                address_wrapper.region_name, address_wrapper.macro_region_name)

        search_objects_url = self.SEARCH_OBJECTS_BY_ADDRESS_URL.format(
            macro_region_id=macro_region_id, region_id=region_id,
            street_name=address_wrapper.street_name,
            house_number=address_wrapper.house_number,
            house_building=address_wrapper.house_building,
            house_structure=address_wrapper.house_structure,
            apartment=address_wrapper.apartment)

        logger.info(f'search_objects_url: {search_objects_url}')
        logger.info('Trying to download rosreestr objects')
        response = self._http_client.get(search_objects_url)

        objects = self._get_response_body(response)
        if objects:
            logger.info('Rosreestr objects were downloaded')
            logger.info(f'Number of rosreestr objects: {len(objects)}')
            return objects
        else:
            return []

    def get_object(self, obj_id: str):
        url = self.SEARCH_DETAILED_OBJECT_BY_ID.format(obj_id)
        logger.info(f'Trying to download detailed object, object_id: {obj_id}')
        response = self._http_client.get(url)
        logger.info(f'Detailed object was downloaded, object_id: {obj_id}')
        return self._get_response_body(response)


class PKK5RosreestrAPIClient:

    # about rosreestr's coordinate system
    # http://holmogori.ru/govinfo/rosreestr/media/2017/4/12/o-primenyaemyih-sistemah-koordinat-dlya-vedeniya-egrn/
    # about МСК
    # https://geostart.ru/post/312

    BASE_URL = 'https://pkk5.rosreestr.ru/api'
    SEARCH_OBJECT_BY_CADASTRAL_ID = (
        BASE_URL + '/features/{object_type}?text={{cadastral_id}}&limit={{limit}}&'
        + 'tolerance={{tolerance}}')
    SEARCH_OBJECT_BY_CADASTRAL_WITHSKIP_ID = (
        BASE_URL + '/features/{object_type}?text={{cadastral_id}}&limit={{limit}}&'
        + 'tolerance={{tolerance}}&skip={{skip}}')
    SEARCH_OBJECT_BY_COORDINATES = (
        BASE_URL + '/features/{object_type}?text={{lat}}%20{{long}}&limit={{limit}}&'
        + 'tolerance={{tolerance}}')
    SEARCH_BUILDING_BY_COORDINATES_URL = SEARCH_OBJECT_BY_COORDINATES.format(object_type=5)
    SEARCH_BUILDING_BY_CADASTRAL_ID_URL = SEARCH_OBJECT_BY_CADASTRAL_ID.format(object_type=5)
    SEARCH_PARCEL_BY_COORDINATES_URL = SEARCH_OBJECT_BY_COORDINATES.format(object_type=1)
    SEARCH_PARCEL_BY_CADASTRAL_ID_URL = SEARCH_OBJECT_BY_CADASTRAL_ID.format(object_type=1)

    BLOCKLENGTH = 11

    atempt = 4

    def __init__(self, timeout=5, keep_alive=False):
        self._http_client = HTTPClient(timeout=timeout, keep_alive=keep_alive)

    def get_parcel_by_coordinates(self, *, lat, long, limit=11, tolerance=2) -> dict:
        url = self.SEARCH_PARCEL_BY_COORDINATES_URL.format(
            lat=lat, long=long, limit=limit, tolerance=tolerance)
        return self._http_client.get(url).json()

    def get_parcel_by_cadastral_id(self, cadastral_id, limit=11, tolerance=2) -> dict:
        url = self.SEARCH_PARCEL_BY_CADASTRAL_ID_URL.format(
            cadastral_id=cadastral_id, limit=limit, tolerance=tolerance)
        return self._http_client.get(url).json()

    def get_objs_by_geom(self, layerid, geometry, limit=11, tolerance=2, skip = 0) -> dict:
        url = self.SEARCH_OBJECT_BY_CADASTRAL_WITHSKIP_ID.format(object_type=layerid)
        url = url.format(cadastral_id='В границах объектов пользователя', limit=limit, tolerance=tolerance, skip=skip)
        d = {}
        d['kip'] = 0
        d['skip'] = skip
        d['limit'] = limit
        d['tolerance'] = tolerance
        d['searchInUserObjects'] = 'true'
        d['source'] = ''
        d['sq'] = geometry
        denc = urllib.parse.urlencode(d)
        denc = denc.encode('ascii')
        req = self._http_client._make_request(self._http_client.POST_HTTP_METHOD, url, data=denc)
        req.close()
        return req.json()

    def get_kns_by_geom_all(self, layerid, geometry, tolerance=16) -> dict:
        res = []
        cnt = 1
        _skip = 0
        l = self.BLOCKLENGTH
        while cnt > 0:
            if _skip > 0:
                time.sleep(0)

            tempres = self.get_kns_by_geom(layerid, geometry, tolerance=tolerance, limit=l, skip=_skip)
            cnt = tempres.__len__()
            res = res + tempres
            if cnt < l:
                break            
            _skip = _skip + l + 1

        return res

    def get_kns_by_geom(self, layerid, geometry, limit=11, tolerance=16, skip = 0) -> dict:
        res = []
        j = None

        _atempt_ = self.atempt

        while _atempt_ > 0:
            try:
                j = self.get_objs_by_geom(layerid, geometry, limit, tolerance, skip)
                _atempt_ = 0
            except :
                self._http_client.ChangeAgent()
                _atempt_ = _atempt_ - 1
                time.sleep(2)
            
        if j:
            fs = j['features']
            if fs :
                for fea in fs:
                    cn = fea['attrs']['cn']
                    res.append(cn)

        return res


    def get_building_by_cadastral_id(self, cadastral_id, limit=11, tolerance=16) -> dict:
        url = self.SEARCH_BUILDING_BY_CADASTRAL_ID_URL.format(
            cadastral_id=cadastral_id, limit=limit, tolerance=tolerance)
        return self._http_client.get(url).json()

    def get_building_by_coordinates(self, *, lat, long, limit=11, tolerance=16) -> dict:
        url = self.SEARCH_BUILDING_BY_COORDINATES_URL.format(
            lat=lat, long=long, limit=limit, tolerance=tolerance)
        return self._http_client.get(url).json()
'''
req = urllib.request.Request('https://pkk5.rosreestr.ru/api/features/1') 
req.add_header('referer', 'https://pkk5.rosreestr.ru/')
data = {}
data['kip'] = 0
data['limit'] = 11
data['tolerance'] = 1
data['searchInUserObjects'] = 'true'
data['sq'] = {"type":"GeometryCollection","geometries":[{"type":"Polygon","coordinates":[[[72.19309376312273,55.88630697752112],[72.19569014144922,55.885259983320495],[72.19472454620383,55.883912087134085],[72.19107674194348,55.883575105773744],[72.1889309747315,55.88506742958821],[72.18933867050178,55.886451388297864],[72.19309376312273,55.88630697752112]]],"bbox":[72.1889309747315,55.883575105773744,72.19569014144922,55.886451388297864]}]}
data1 = urllib.parse.urlencode(data)
data1 = data1.encode('ascii')
req.data = data1
resp = urllib.request.urlopen(req)
respdata = resp.read()
respdecode = respdata.decode('utf8')
print(respdecode)
json_data = json.loads(respdecode)
print(json_data)
features = json_data['features']
'''