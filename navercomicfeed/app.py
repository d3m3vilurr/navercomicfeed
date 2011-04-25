""":mod:`navercomicfeed.app`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This module several web pages including: lists of comic series, Atom feed XML
pages for series, a proxy that works around referrer-blocking images,
an initial RDBMS schema installation script.

.. data:: WEBTOON_LIST_URL

   The URL of Naver Comic webtoons list.

.. data:: BESTCHALLENGE_LIST_URL

   The URL of Naver Comic best challenge comics list.

.. data:: URL_TYPES

   The URL templates.

.. function:: app

   The Flask application, that also is a WSGI application.

.. data:: cache

   The cache object powered by Flask-Cache.

"""
import os
import os.path
import re
import functools
import itertools
import contextlib
import hmac
import hashlib
import urlparse
import logging
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO
from flask import *
from flaskext.cache import Cache
import lxml.html
import werkzeug.urls
import sqlalchemy
from navercomicfeed.comic import *
import navercomicfeed.pool
import navercomicfeed.urlfetch


WEBTOON_LIST_URL = 'http://comic.naver.com/webtoon/creation.nhn?view=list'
BESTCHALLENGE_LIST_URL = 'http://comic.naver.com/genre/bestChallenge.nhn'
URL_TYPES = {
    'webtoon': 'http://comic.naver.com/webtoon/list.nhn?titleId={0}',
    'challenge': 'http://comic.naver.com/challenge/list.nhn?titleId={0}',
    'bestchallenge': 'http://comic.naver.com/bestChallenge/list.nhn?titleId={0}'
}
POOL_SIZE = 10


app = Flask(__name__)
app.config['IMGPROXY_URL'] = 'http://imgproxy.dahlia.kr/image.php'
try:
    config_env = os.environ['NAVERCOMICFEED_CONFIG']
    app.config.from_pyfile(os.path.abspath(config_env))
    del config_env
except (KeyError, IOError):
    pass
cache = Cache(app)


def admin_only(function):
    """The decorator that makes view function to allow only administrators.
    It assumes the configuration variable :data:`ADMIN_PRED_FN`, a function
    that takes ``user`` and ``password`` and returns whether the given
    credential has an administrator permission.

    .. function:: config.ADMIN_PRED_FN(user, password)

       The predicate function that tests a ``user``/``password`` credential
       has an administrator permission.

       :param user: an username inputted through HTTP basic auth
       :type user: :class:`basestring`
       :param password: a password inputted through HTTP basic auth
       :type password: :class:`basestring`
       :returns: whether the given credential has an administrator permission
       :rtype: :class:`bool`

    If it isn't defined, it denies all access tries.

    :param function: a view function
    :type function: callable object
    :returns: a decorated view functions which allows only administrators
    :rtype: callable object

    """
    @functools.wraps(function)
    def replaced_function(*args, **kwargs):
        try:
            admin_pred_fn = app.config['ADMIN_PRED_FN']
        except KeyError:
            abort(403)
        else:
            auth = request.authorization
            if auth:
                user = auth.username
                password = auth.password
            else:
                user = password = None
            if not auth or not admin_pred_fn(user, password):
                realm = 'NaverComicFeed Administrator'
                headers = {'WWW-Authenticate':
                           'Basic realm="{0}"'.format(realm)}
                return Response(realm, 401, headers)
        return function(*args, **kwargs)
    return replaced_function


@app.before_request
def before_request():
    """Sets up the database engine and the ORM session."""
    g.engine = sqlalchemy.create_engine(app.config['DATABASE'])
    Session.configure(bind=g.engine)


@app.context_processor
def context_processor():
    return {'proxy_url_for': proxy_url_for}


@app.route('/')
def home():
    return render_template('home.html')


def get_title_thumbnail_url(title_id, pair=False, default=None):
    """Gets the thumbnail image URL of the title.
    
    :param title_id: the title id
    :type title_id: :class:`int`, :class:`long`
    :param pair: if ``True`` it returns a :class:`tuple`. otherwise it returns
                 just a thumbnail url. ``False`` by default
    :type pair: :class:`bool`
    :param default: a default value used when there's no cache. if not present,
                    gets thumbnail url from web
    :returns: a pair of ``(title_id, thumbnail_url)`` or just a thubnail url
              if ``pair`` is ``False``
    :rtype: :class:`tuple`, :class:`basestring`

    """
    logger = logging.getLogger(__name__ + '.get_title_thumbnail_url')
    cache_key = 'title_thumbnail_{0}'.format(title_id)
    cached = cache.get(cache_key)
    if cached:
        logger.info('used cached of title %d', title_id)
        return (title_id, cached) if pair else cached
    if default is not None:
        return default
    url = URL_TYPES['webtoon'].format(title_id)
    with navercomicfeed.urlfetch.fetch(url, cache, 120) as f:
        html = f.read()
        logger.info('downloaded title %d from %s', title_id, url)
        m = re.search(r'<div class="thumb">(.+?)</div>', html)
        html = m.group(1)
        m = re.search(r'src="(https?://.+?)"', html)
        img_src = m.group(1)
        cache.set(cache_key, img_src)
        return (title_id, img_src) if pair else img_src


@app.route('/thumbnails/<int:title_id>')
def title_thumbnail_url(title_id):
    url = get_title_thumbnail_url(title_id)
    return redirect(proxy_url_for(url), 307)


def comics_with_thumbnails(comics):
    get_url = functools.partial(url_for, 'title_thumbnail_url')
    comics = [(id, title,
               get_title_thumbnail_url(id, default=get_url(title_id=id)))
              for id, title in comics]
    comics.sort(key=lambda (_, title, __): title)
    return comics


def cached_comics(cache_key, comics):
    result = cache.get(cache_key)
    if not result:
        result = []
        ids = set()
        for title_id, title in comics:
            if title_id not in ids:
                result.append((title_id, unicode(title)))
                ids.add(title_id)
        result.sort(key=lambda (_, title): title)
        cache.set(cache_key, result)
    return result


def webtoon_comics():
    html = lxml.html.parse(WEBTOON_LIST_URL)
    links = html.xpath('//*[@id="content"]//*[@class="section"]/ul/li/a')
    for a in links:
        title = a.attrib['title']
        href = a.attrib['href']
        query = href[href.index('?') + 1:]
        title_id = int(werkzeug.urls.url_decode(query)['titleId'])
        yield title_id, title


@app.route('/webtoon')
def webtoon_list():
    comics = cached_comics('webtoon_list', webtoon_comics())
    comics = comics_with_thumbnails(comics)
    return render_template('webtoon_list.html', comics=comics)


def bestchallenge_comics():
    logger = logging.getLogger(__name__ + '.bestchallenge_comics')
    url_format = BESTCHALLENGE_LIST_URL + '?page={0}'
    last_url = url_format.format(999999)
    with navercomicfeed.urlfetch.fetch(last_url, cache, 120) as f:
        html = lxml.html.parse(f)
    logger.info(last_url)
    last = html.xpath('//*[@id="content"]//*[contains(concat(" ", @class,'
                      '" "), " pagenavigation ")]/*[@class="current"]/text()')
    last_html = html
    last = int(last[0])
    def get_html(page):
        if page == last:
            return last_html
        url = url_format.format(page)
        with navercomicfeed.urlfetch.fetch(url, cache, 120) as f:
            logger.info(url)
            html = lxml.html.parse(f)
        return html
    pool = navercomicfeed.pool.Pool(POOL_SIZE)
    htmls = pool.map(get_html, xrange(1, last + 1))
    for html in htmls:
        links = html.xpath('//*[@id="content"]//table[@class="challengeList"]'
                           '//td/*[@class="fl"]/a')
        for a in links:
            href = a.attrib['href']
            query = href[href.index('?') + 1:]
            title_id = int(werkzeug.urls.url_decode(query)['titleId'])
            yield title_id, a.xpath('./img/@title')[0]


@app.route('/bestchallenge')
def bestchallenge_list():
    comics = cached_comics('bestchallenge_list', bestchallenge_comics())
    comics = comics_with_thumbnails(comics)
    return render_template('bestchallenge_list.html', comics=comics)


@app.route('/etc')
def etc():
    try:
        url = request.values['url']
    except KeyError:
        return render_template('etc.html')
    p = urlparse.urlparse(url)
    if p.scheme in ('http', 'https') and p.hostname == 'comic.naver.com':
        m = re.match(r'^/(webtoon|bestChallenge|challenge)/', p.path)
        if m:
            type = m.group(1).lower()
            query = werkzeug.urls.url_decode(p.query)
            try:
                title_id = query['titleId']
            except KeyError:
                pass
            else:
                url = url_for('feed', type=type, title_id=title_id, limit=15)
                return redirect(url)
    return render_template('etc.html', url=url, error=True)


def proxy_url_for(url, ignore_relative_path=True):
    """Returns a proxied image ``url``.

    :param url: an image url
    :type url: :class:`basestring`
    :param ignore_relative_path: returns the given ``url`` without any
                                 modification if ``url`` doesn't start with
                                 ``http://`` or ``https://``
    :returns: an image url of proxy version
    :rtype: :class:`basestring`

    """
    if ignore_relative_path and \
       not (url.startswith('http://') or url.startswith('https://')):
        return url
    try:
        imgproxy_key = app.config['IMGPROXY_KEY']
        imgproxy_secret_key = app.config['IMGPROXY_SECRET_KEY']
        imgproxy_url = app.config['IMGPROXY_URL']
    except KeyError:
        return url_for('image_proxy', url=url, _external=True)
    else:
        hash = hmac.new(imgproxy_secret_key, url, hashlib.sha256)
        sig = hash.hexdigest()
        query = {'url': url, 'key': imgproxy_key, 'sig': sig}
        return imgproxy_url + '?' + werkzeug.urls.url_encode(query)


@app.route('/<any(webtoon,bestchallenge,challenge):type>/<int:title_id>.xml')
@cache.cached(timeout=120)
def feed(type, title_id):
    session = Session()
    url = URL_TYPES[type].format(title_id)
    title = Title(url, session, cache=cache)
    limit = request.values.get('limit', '')
    try:
        limit = int(limit)
    except ValueError:
        pass
    else:
        title = title[:limit]
    xml = render_template('feed.xml', title=title)
    types = ['text/xml', 'application/atom+xml']
    type = request.accept_mimetypes.best_match(types)
    return Response(response=xml, content_type=type)


@app.route('/img')
def image_proxy():
    imgproxy_cfgs = 'URL', 'KEY', 'SECRET_KEY'
    if all('IMGPROXY_' + c in app.config for c in imgproxy_cfgs):
        abort(403)
    url = request.values['url']
    key = hashlib.md5(url).hexdigest()
    type_key = 'imageproxy_t_{0}'.format(key)
    body_key = 'imageproxy_b_{0}'.format(key)
    content_type = cache.get(type_key)
    body = cache.get(body_key)
    if content_type and body:
        return Response(response=body, content_type=content_type)
    def fetch():
        with navercomicfeed.urlfetch.fetch(url, cache) as f:
            content_type = f.info()['Content-Type']
            yield content_type
            bytes = StringIO.StringIO()
            while True:
                buffer = f.read(4096)
                if buffer:
                    yield buffer
                    bytes.write(buffer)
                else:
                    break
        cache.set(type_key, content_type)
        cache.set(body_key, bytes.getvalue())
    it = fetch()
    content_type = it.next()
    return Response(response=it, content_type=content_type)


@app.route('/admin/setup')
@admin_only
def admin_setup():
    Base.metadata.create_all(g.engine)
    return 'Successfully tables created.'


@app.route('/admin/clearcache')
@admin_only
def admin_clear_cache():
    if hasattr(cache, 'cache') and hasattr(cache.cache, 'clear'):
        cache.cache.clear()
        return 'Cached data got cleared.'
    return 'Cached data cannot be cleared.'


@app.route('/admin/urlfetch')
@admin_only
def admin_urlfetch():
    try:
        cache_timeout = int(request.values['cache_timeout'])
    except (KeyError, TypeError):
        cache_timeout = None
    try:
        url = request.values['url']
    except KeyError:
        response = None
        encoding = None
    else:
        response = navercomicfeed.urlfetch.fetch(url, cache, cache_timeout)
        type = response.headers['Content-Type']
        encoding = re.search(r';\s*charset\s*=\s*([-a-z0-9_.]+)', type, re.I)
        encoding = encoding and encoding.group(1)
    with response:
        return render_template('admin/urlfetch.html',
                               response=response,
                               encoding=encoding,
                               cache_timeout=cache_timeout)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    app.run(debug=True)

