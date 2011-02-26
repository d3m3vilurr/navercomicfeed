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
import urllib2
import contextlib
import hmac
import hashlib
import urlparse
from flask import *
from flaskext.cache import Cache
import lxml.html
import werkzeug.urls
import sqlalchemy
from navercomicfeed.comic import *


WEBTOON_LIST_URL = 'http://comic.naver.com/webtoon/creation.nhn?view=list'
BESTCHALLENGE_LIST_URL = 'http://comic.naver.com/genre/bestChallenge.nhn'
URL_TYPES = {
    'webtoon': 'http://comic.naver.com/webtoon/list.nhn?titleId={0}',
    'challenge': 'http://comic.naver.com/challenge/list.nhn?titleId={0}',
    'bestchallenge': 'http://comic.naver.com/bestChallenge/list.nhn?titleId={0}'
}


app = Flask(__name__)
app.config['IMGPROXY_URL'] = 'http://imgproxy.dahlia.kr/image.php'
try:
    config_env = os.environ['NAVERCOMICFEED_CONFIG']
    app.config.from_pyfile(os.path.abspath(config_env))
    del config_env
except (KeyError, IOError):
    pass
cache = Cache(app)


@app.before_request
def before_request():
    """Sets up the database engine and the ORM session."""
    g.engine = sqlalchemy.create_engine(app.config['DATABASE'])
    Session.configure(bind=g.engine)


@app.route('/')
def home():
    return ''


@app.route('/webtoon')
@cache.cached(timeout=3600 * 6)
def webtoon_list():
    html = lxml.html.parse(WEBTOON_LIST_URL)
    links = html.xpath('//*[@id="content"]//*[@class="section"]/ul/li/a')
    comics = {}
    for a in links:
        title = a.attrib['title']
        href = a.attrib['href']
        query = href[href.index('?') + 1:]
        title_id = int(werkzeug.urls.url_decode(query)['titleId'])
        comics[title_id] = title
    return render_template('webtoon_list.html', comics=comics)


def bestchallenge_comics():
    page = 1
    url = BESTCHALLENGE_LIST_URL + '?page={0}'
    prev_title_ids = set()
    while True:
        html = lxml.html.parse(url.format(page))
        links = html.xpath('//*[@id="content"]//table[@class="challengeList"]'
                           '//td/*[@class="fl"]/a')
        title_ids = set()
        for a in links:
            href = a.attrib['href']
            query = href[href.index('?') + 1:]
            title_id = int(werkzeug.urls.url_decode(query)['titleId'])
            yield title_id, a.xpath('./img/@title')[0]
            title_ids.add(title_id)
        if title_ids.issubset(prev_title_ids):
            break
        prev_title_ids.update(title_ids)
        page += 1


@app.route('/bestchallenge')
@cache.cached(timeout=3600 * 6)
def bestchallenge_list():
    comics = dict(bestchallenge_comics())
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
            type = m.group(1)
            query = werkzeug.urls.url_decode(p.query)
            try:
                title_id = query['titleId']
            except KeyError:
                pass
            else:
                return redirect(url_for('feed', type=type, title_id=title_id))
    return render_template('etc.html', url=url, error=True)


@app.route('/<any(webtoon,bestchallenge,challenge):type>/<int:title_id>.xml')
@cache.cached(timeout=120)
def feed(type, title_id):
    session = Session()
    url = URL_TYPES[type].format(title_id)
    title = Title(url, session)
    limit = request.values.get('limit', '')
    try:
        limit = int(limit)
    except ValueError:
        pass
    else:
        title = title[:limit]
    try:
        imgproxy_key = app.config['IMGPROXY_KEY']
        imgproxy_secret_key = app.config['IMGPROXY_SECRET_KEY']
        imgproxy_url = app.config['IMGPROXY_URL']
    except KeyError:
        def proxy_fn(url):
            return url_for('image_proxy', url=url, _external=True)
    else:
        def imgproxy_sig(url):
            hash = hmac.new(imgproxy_secret_key, url, hashlib.sha256)
            return hash.hexdigest()
        def proxy_fn(url):
            query = {'url': url, 'key': imgproxy_key, 'sig': imgproxy_sig(url)}
            return imgproxy_url + '?' + werkzeug.urls.url_encode(query)
    xml = render_template('feed.xml', title=title, proxy_url_for=proxy_fn)
    types = ['text/xml', 'application/atom+xml']
    type = request.accept_mimetypes.best_match(types)
    return Response(response=xml, content_type=type)


@app.route('/img')
@cache.cached(timeout=3600 * 6)
def image_proxy():
    imgproxy_cfgs = 'URL', 'KEY', 'SECRET_KEY'
    if all('IMGPROXY_' + c in app.config for c in imgproxy_cfgs):
        abort(403)
    def fetch():
        url = request.values['url']
        with contextlib.closing(urllib2.urlopen(url)) as f:
            yield f.info()['Content-Type']
            while True:
                buffer = f.read(4096)
                if buffer:
                    yield buffer
                else:
                    break
    it = fetch()
    content_type = it.next()
    return Response(response=it, content_type=content_type)


@app.route('/admin/setup')
def admin_setup():
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
        if not admin_pred_fn(user, password):
            realm = 'NaverComicFeed Administrator'
            headers = {'WWW-Authenticate': 'Basic realm="{0}"'.format(realm)}
            return Response(realm, 401, headers)
    Base.metadata.create_all(g.engine)
    return 'Successfully tables created.'


if __name__ == '__main__':
    app.run(debug=True)

