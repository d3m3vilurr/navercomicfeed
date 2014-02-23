""":mod:`navercomicfeed.urlfetch` --- Thin wrapper of :mod:`urllib2`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Provides a simple cache-enabled wrapper of :mod:`urllib2`.

"""
import urllib2
import hashlib


def fetch(url, cache=None, cache_timeout=None, referer=None):
    """"Fetches the ``url`` then returns its response.

    :param url: an url to request
    :type url: :class:`basestring`
    :param cache: an optional cache object
    :type cache: :class:`werkzeug.contrib.cache.BaseCache`
    :param cache_timeout: an optional timeout of cache
    :param referer: an referer url of request
    :type url: :class:`basestring`
    :returns: the response
    :rtype: :class:`BaseResponse`

    """
    cache_key = 'urlfetch_' + hashlib.sha1(url).hexdigest()
    if cache:
        cached = cache.get(cache_key)
        if cached:
            return CachedResponse(url, cached)
    req = urllib2.Request(url)
    if referer:
        req.add_header('Referer', referer)
    f = urllib2.urlopen(req)
    return WrappedResponse(f, cache, cache_key, cache_timeout)


#: Alias of :func:`fetch()`.
urlopen = fetch


class BaseResponse(object):
    """The base interface of :class:`WrappedResponse` and
    :class:`CachedResponse` objects. It imitates the interface of
    :func`urllib2.urlopen()` function's return value.

    """

    __slots__ = ()

    @property
    def url(self):
        return self.geturl()

    @property
    def code(self):
        return self.getcode()

    @property
    def headers(self):
        return self.info()

    def __iter__(self):
        return self

    def next(self):
        line = self.readline()
        if line:
            return line
        raise StopIteration()

    def readlines(self):
        return list(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def geturl(self):
        raise NotImplementedError('should be overridden')

    def getcode(self):
        raise NotImplementedError('should be overridden')

    @property
    def msg(self):
        raise NotImplementedError('should be overridden')

    def info(self):
        raise NotImplementedError('should be overridden')

    def read(self, size=-1):
        raise NotImplementedError('should be overridden')

    def readline(self):
        raise NotImplementedError('should be overridden')

    def close(self):
        raise NotImplementedError('should be overridden')


class WrappedResponse(BaseResponse):

    __slots__ = 'response', 'cache', 'cache_key', 'cache_timeout', 'cached'

    def __init__(self, source, cache=None, cache_key=None, cache_timeout=None):
        self.response = source
        self.cache = cache
        self.cache_key = cache_key or hashlib.sha1(self.url).hexdigest()
        self.cache_timeout = cache_timeout
        self.cached = []

    def geturl(self):
        return self.response.geturl()

    def getcode(self):
        return self.response.getcode()

    @property
    def msg(self):
        return self.response.msg

    def info(self):
        return self.response.info()

    def read(self, size=-1):
        if self.response and self.response.read:
            arg = () if size < 0 else (size,)
            data = self.response.read(*arg)
            if self.cache:
                self.cached.append(data)
            return data
        return ''

    def readline(self):
        data = self.response.readline()
        if self.cache:
            self.cached.append(data)
        return data

    def close(self):
        self.read()
        self.response.close()
        if self.cache:
            record = self.code, self.msg, self.info(), ''.join(self.cached)
            self.cache.set(self.cache_key, record, self.cache_timeout)


class CachedResponse(BaseResponse):

    __slots__ = 'url_', 'cache_data', 'offset'

    def __init__(self, url, cache_data):
        self.url_ = url
        self.cache_data = list(cache_data)
        self.offset = 0

    def geturl(self):
        return self.url_

    def getcode(self):
        return self.cache_data[0]

    @property
    def msg(self):
        return self.cache_data[1]

    def info(self):
        return self.cache_data[2]

    def read(self, size=-1):
        body = self.cache_data[3]
        if size < 0:
            return body[self.offset:]
        end = self.offset + size
        retval = body[self.offset:end]
        self.offset = end
        return retval

    def readline(self):
        body = self.cache_data[3]
        try:
            offset = body.index('\n', self.offset) + 1
        except ValueError:
            offset = len(body)
        line = body[self.offset:offset]
        self.offset = offset
        return line

    def close(self):
        pass

