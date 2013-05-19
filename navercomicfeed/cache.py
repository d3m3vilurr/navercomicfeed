""":mod:`naverwebcomic.cache` --- Custom cache backends
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

It implements custom cache backends powered by :mod:`werkzeug.contrib.cache`
and :mod:`flask.ext.cache`.

Currently, it implements a Redis backend only.

"""
import itertools
try:
    import cPickle as pickle
except ImportError:
    import pickle
import flask
import flask.ext.cache
import werkzeug.contrib.cache


class RedisCache(werkzeug.contrib.cache.BaseCache):
    """A cache that uses Redis as backend.

    :param redis_client: a Redis client
    :type redis_client: :class:`redis.Redis`
    :param default_timeout: the default timeout that is used if no timeout
                            is specified on :meth:`set()`.

    .. seealso:: Package redis_

    .. _redis: https://github.com/andymccurdy/redis-py

    """

    @staticmethod
    def dumps(value):
        if isinstance(value, (int, long, float)):
            return str(value)
        return '=' + pickle.dumps(value)

    @staticmethod
    def loads(value):
        if value.startswith('='):
            return pickle.loads(value[1:])
        return eval(value)

    def __init__(self, redis_client, default_timeout=300):
        super(RedisCache, self).__init__(default_timeout=default_timeout)
        self.redis = redis_client

    def add(key, value, timeout=None):
        pipe = self.redis.pipeline()
        value = self.dumps(value)
        pipe.setnx(key, value).expire(key, timeout or self.default_timeout)
        pipe.execute()

    def clear(self):
        self.redis.flushdb()

    def dec(self, key, delta=1):
        self.redis.decr(key, amount=delta)

    def delete(self, key):
        self.redis.delete(key)

    def delete_many(self, *keys):
        self.redis.delete(*keys)

    def get(self, key):
        v = self.redis.get(key)
        return v and self.loads(v)

    def get_dict(self, *keys):
        values = map(self.loads, self.redis.mget(keys))
        return dict(itertools.izip(keys, values))

    def get_many(self, *keys):
        return map(self.loads, self.redis.mget(keys))

    def inc(self, key, delta=1):
        self.redis.incr(key, amount=delta)

    def set(self, key, value, timeout=None):
        timeout = timeout or self.default_timeout
        self.redis.setex(key, self.dumps(value), timeout)

    def set_many(self, mapping, timeout=None):
        pipe = self.redis.pipeline()
        mappding = dict((k, self.dumps(v)) for k, v in mapping.iteritems())
        pipe.mset(mapping).expire(key, timeout or self.default_timeout)
        pipe.execute()


def redis(app, args, kwargs):
    """A Redis backend for Flask-Cache. Set ``CACHE_TYPE`` to
    ``'styleshare.cache.redis'`` in your Flask configuration.

    There are additional configuration values for it:

    - ``CACHE_REDIS_DB`` (required)
    - ``CACHE_REDIS_HOST``
    - ``CACHE_REDIS_PORT``
    - ``CACHE_REDIS_PASSWORD``
    - ``CACHE_REDIS_SOCKET_TIMEOUT``

    .. warning:: It requires redis_ package (known as **redis-py** also).

    .. redis_: https://github.com/andymccurdy/redis-py

    """
    from redis import Redis
    client = Redis(db=app.config['CACHE_REDIS_DB'],
                   host=app.config.get('CACHE_REDIS_HOST'),
                   port=app.config.get('CACHE_REDIS_PORT'),
                   password=app.config.get('CACHE_REDIS_PASSWORD'),
                   socket_timeout=app.config.get('CACHE_REDIS_SOCKET_TIMEOUT'))
    args.append(client)
    return RedisCache(*args, **kwargs)

