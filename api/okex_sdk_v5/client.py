import copy
import threading

import gevent
import requests
from requests.adapters import HTTPAdapter
import json
from . import consts as c, utils, exceptions


def _build_session():
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=32, pool_maxsize=64, max_retries=0)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


def _run_blocking(func, *args, **kwargs):
    # 主线程承载 gevent hub，阻塞式 HTTP 会冻结全部协程，故卸载到线程池；工作线程内直接执行
    # 该判定依赖全仓未启用 gevent.monkey.patch_all()（WsPublic 的 asyncio 循环需要真实线程）
    if threading.current_thread() is threading.main_thread():
        return gevent.get_hub().threadpool.apply(func, args, kwargs)
    return func(*args, **kwargs)


class Client(object):

    def __init__(self, api_key, api_secret_key, passphrase, use_server_time=False, flag='1'):

        self.API_KEY = api_key
        self.API_SECRET_KEY = api_secret_key
        self.PASSPHRASE = passphrase
        self.use_server_time = use_server_time
        self.flag = flag
        self._local = threading.local()

    def __deepcopy__(self, memo):
        client = self.__class__.__new__(self.__class__)
        memo[id(self)] = client
        for name, value in self.__dict__.items():
            if name != "_local":
                setattr(client, name, copy.deepcopy(value, memo))
        # 深拷贝时重建线程本地状态，避免副本共享原客户端的连接会话
        client._local = threading.local()
        return client

    @property
    def _session(self):
        # requests.Session 非线程安全，线程池工作线程各持一份，既复用连接池又互不干扰
        session = getattr(self._local, "session", None)
        if session is None:
            session = _build_session()
            self._local.session = session
        return session

    def _session_request(self, method_name, url, **kwargs):
        # 必须在真正执行请求的线程内取 Session：卸载到线程池时调用线程与执行线程不同，
        # 提前取会让全部工作线程共用调用线程那一份，线程隔离失效
        return _run_blocking(lambda: getattr(self._session, method_name)(url, **kwargs))

    def _request(self, method, request_path, params, timeout=(2, 3)):

        if method == c.GET:
            request_path = request_path + utils.parse_params_to_str(params)
        # url
        url = c.API_URL + request_path

        timestamp = utils.get_timestamp()

        # sign & header
        if self.use_server_time:
            timestamp = self._get_timestamp()

        body = json.dumps(params) if method == c.POST else ""

        sign = utils.sign(utils.pre_hash(timestamp, method, request_path, str(body)), self.API_SECRET_KEY)
        header = utils.get_header(self.API_KEY, sign, timestamp, self.PASSPHRASE, self.flag)

        if method == c.GET:
            response = self._session_request('get', url, headers=header, timeout=timeout)
        elif method == c.POST:
            response = self._session_request('post', url, data=body, headers=header, timeout=timeout)
        else:
            raise ValueError(f"unsupported http method: {method}")

        if not str(response.status_code).startswith('2'):
            raise exceptions.OkexAPIException(response)

        return response.json()

    def _request_without_params(self, method, request_path, timeout=(3, 5)):
        return self._request(method, request_path, {}, timeout)

    def _request_with_params(self, method, request_path, params, timeout=(3, 5)):
        return self._request(method, request_path, params, timeout)

    def _get_timestamp(self):
        url = c.API_URL + c.SERVER_TIMESTAMP_URL
        response = self._session_request('get', url, timeout=(2, 3))
        if response.status_code == 200:
            return response.json()['ts']
        else:
            return ""
