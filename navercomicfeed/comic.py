""":mod:`navercomicfeed.comic` --- Comics
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This module implements the crawler and RDMBS-powered cache for it.

.. class:: Session

   The ORM session class.

.. class:: Base

   The declarative base class for object-relational mapping.

.. data:: POOL_SIZE

   The size of workers for fetching comics. 20 by default.

.. data:: TZINFO

   The time zone of Naver Comic service. Asia/Seoul by default.

.. data:: ARTIST_URL_FORMAT
.. data:: COMIC_XPATH
.. data:: COMIC_TITLE_XPATH
.. data:: COMIC_URL_XPATH
.. data:: COMIC_PUBLISHED_AT_XPATH
.. data:: COMIC_IMAGE_URLS_XPATH
.. data:: COMIC_DESCRIPTION_XPATH

   Several :class:`lxml.etree.XPath` for crawling.

"""
import re
import collections
import logging
import urlparse
import datetime
import pytz
import lxml.etree
import lxml.html
import sqlalchemy
import sqlalchemy.orm
import sqlalchemy.ext.declarative
import sqlalchemy.sql.functions
import futureutils
import urlfetch
import json
import HTMLParser
from pool import Pool


INFO_URL = 'https://comic.naver.com/api/article/list/info?titleId={0}'
LIST_URL = 'https://comic.naver.com/api/article/list?titleId={0}'
DETAIL_EPISODE_URL = 'https://comic.naver.com/{0}/detail?titleId={1}&no={2}'

TITLE_TYPE = {
    'WEBTOON': 'webtoon',
    'BEST_CHALLENGE': 'bestChallenge',
    'CHALLENGE': 'challenge',
}

POOL_SIZE = 20
TZINFO = pytz.timezone('Asia/Seoul')
ARTIST_URL_FORMAT = 'https://comic.naver.com/artistTitle.nhn?artistId={0.id}'
COMIC_XPATH = lxml.etree.XPath('//*[@id="content"]/table[@class="viewList"]'
                               '//tr/td[@class="title"]/..')
COMIC_TITLE_XPATH = lxml.etree.XPath('.//td[@class="title"]/a/text()')
COMIC_URL_XPATH = lxml.etree.XPath('.//td[@class="title"]/a/@href')
COMIC_PUBLISHED_AT_XPATH = lxml.etree.XPath('.//td[@class="num"]/text()')
COMIC_IMAGE_URLS_XPATH = lxml.etree.XPath('//*[@id="comic_view_area"]'
                                          '//*[@class="wt_viewer"]/img/@src')
COMIC_IMAGE_URLS_XPATH2 = lxml.etree.XPath('//*[@id="comic_view_area"]'
                                           '//*[@class="flip-cached_page"]'
                                           '//img[@src="" and starts-with('
                                           '@class, "real_url(")]')
COMIC_IMAGE_URLS_JAVASCRIPT_PATTERN = re.compile('imageList = (?P<urls>\[.+\])')
COMIC_DESCRIPTION_XPATH = lxml.etree.XPath('//*[@id="comic_view_area"]'
                                           '//*[@class="writer_info"]/p/text()')
COMIC_DESCRIPTION_JAVASCRIPT_PATTERN = re.compile('"authorWords":\"(?P<desc>.+)\"')

Session = sqlalchemy.orm.sessionmaker(autocommit=True)
Session = sqlalchemy.orm.scoped_session(Session)
Base = sqlalchemy.ext.declarative.declarative_base()

unescape = HTMLParser.HTMLParser().unescape

class Title(object):
    """A comic title that has one or more series of comics.

    :param url: an :attr:`url` of the comic title
    :type url: :class:`basestring`
    :param session: an orm :attr:`session` instance
    :type session: :class:`Session`
    :param offset: an optional offset. internal-use only. default is 0
    :type offset: :class:`int`, :class:`long`
    :param limit: an optional list size. internal-use only. ``None`` by default
    :type limit: :class:`int`, :class:`long`

    .. attribute:: url

       The URL of the comic title.

    .. attribute:: session

       The ORM session.

    .. attribute:: offset

       A :class:`Title` object can be limited by its offset. Internal-use
       only purpose.

    .. attribute:: limit

       A :class:`Title` object can be limited by its list size. Internal-use
       only purpose.

    """

    __slots__ = ('title_id', 'session', 'offset', 'limit', 'cache', '_title',
                 '_description', '_artists', '_info', '_list', '_list_page')

    def __init__(self, title_id, session, offset=0, limit=None, cache=None):
        self.title_id = title_id
        self.session = session
        self.offset = offset
        self.limit = limit
        self.cache = None

    def _get_info(self):
        logger = self.get_logger('_get_info')
        url = INFO_URL.format(self.title_id)
        if not hasattr(self, '_info'):
            with urlfetch.fetch(url, self.cache) as f:
                logger.info('url fetched: %s', url)
                self._info = json.load(f)
        else:
            logger.info('cache hit: %s', url)
        return self._info

    def _get_list(self, page=None, pair=False):
        logger = self.get_logger('_get_list')
        p = page or 1
        url = LIST_URL.format(self.title_id)
        params = url, ('&' if '?' in url else '?'), p
        url = '{0}{1}page={2}'.format(*params)
        if not hasattr(self, '_list') or page and self._list_page != page:
            with urlfetch.fetch(url, self.cache) as f:
                logger.info('url fetched: %s', url)
                self._list = json.load(f)
            self._list_page = page
        else:
            logger.info('cache hit: %s', url)
        if pair:
            return self._list, url
        return self._list

    @property
    def title(self):
        """The title string."""
        if not hasattr(self, '_title'):
            self._title = self._get_info()['titleName'].strip()
        return self._title

    @property
    def description(self):
        """The description string."""
        if not hasattr(self, '_description'):
            self._description = self._get_info()['synopsis'].strip()
        return self._description

    def get_logger(self, name=None):
        cls = type(self)
        names = [cls.__module__, cls.__name__]
        if name:
            names.append(name)
        return logging.getLogger('.'.join(names))

    def _fetch_artists(self, info, ignore_cache=False):
        if not ignore_cache and hasattr(self, '_artists') and self._artists:
            return
        logger = self.get_logger('_fetch_artists')
        self._artists = []
        artists_ids = set()
        for _, authors in info['author'].items():
            for author in authors:
                artist_id = int(author['id'])
                artist_name = author['name']
                artist_url = author.get('blogUrl')
                if artist_id in artists_ids:
                    continue
                artists_ids.add(artist_id)
                self._artists.append(Artist(artist_id, artist_name, artist_url))
        if len(self._artists):
            logger.info('fetched artist list (%d)', len(self._artists))

    @property
    def artists(self):
        """The :class:`Artist` list."""
        if not hasattr(self, '_artists'):
            self._artists = []
            self._fetch_artists(self._get_info())
        return self._artists

    def _fetch_comic_javascript(self, html_string):
        matches = COMIC_IMAGE_URLS_JAVASCRIPT_PATTERN.search(html_string)
        if matches:
            matches = matches.groupdict().get('urls')
            return eval(matches.groupdict().get('urls'))

    def _crawl_comic(self, (no, title, published, comic_url)):
        logger = self.get_logger('_crawl_comic')
        expire = 3600 * 24
        with urlfetch.fetch(comic_url, self.cache, expire) as f:
            logger.info('url fetched: %s', comic_url)
            comic_html = lxml.html.parse(f)
            comic_html_string = lxml.html.tostring(comic_html)
        self._fetch_artists(self._get_info())
        image_urls = COMIC_IMAGE_URLS_XPATH(comic_html)
        if image_urls:
            book = False
            urls = self._fetch_comic_javascript(comic_html_string)
            image_urls = urls or image_urls
        else:
            book = True
            logger.info('book-like comic')
            images = COMIC_IMAGE_URLS_XPATH2(comic_html)
            image_urls = []
            class_re = re.compile(ur'real_url\((https?://.+?)\)')
            for img in images:
                m = class_re.match(img.attrib['class'])
                if m:
                    image_urls.append(m.group(1))
        with urlfetch.fetch(comic_url, self.cache, expire) as f:
            logger.info('url fetched: %s', comic_url)
            desc_matches = COMIC_DESCRIPTION_JAVASCRIPT_PATTERN.search(f.read())
            if desc_matches:
                description = unescape(desc_matches.groupdict().get('desc'))
            else:
                description = '.'
        description = description.decode('utf-8')
        comic = Comic(comic_url, no, title, book, image_urls,
                      description, published)
        logging.info(repr(comic))
        return comic

    @futureutils.future_generator
    def _crawl_list(self):
        logger = self.get_logger('_crawl_list')
        max = sqlalchemy.sql.functions.max
        max_no, = self.session.query(max(StoredComic.no)) \
                              .filter_by(title_id=self.title_id) \
                              .first()
        logger.info('max_no: %r', max_no)
        page = 1
        stopped = False
        no_re = re.compile(r'[?&]no=(\d+)(&|$)')
        crawled_numbers = set()
        while True:
            episodes = self._get_list(page)
            webtoon_level = episodes['webtoonLevelCode']
            title_type = TITLE_TYPE[webtoon_level]
            for article in episodes['articleList']:
                # non free episode
                if article['charge']:
                    continue
                title = article['subtitle']
                no = int(article['no'])
                href = DETAIL_EPISODE_URL.format(title_type, self.title_id, no)
                published = article['serviceDateDescription']
                try:
                    published = datetime.datetime.strptime(
                        re.sub(r'[A-Z]{3} (\d{4})$', r'\1',
                               published.strip()),
                        '%a %b %d %H:%M:%S %Y'
                    )
                except ValueError:
                    published = re.split(r'\D+', published.strip())
                    published = tuple(int(d) for d in published
                                             if re.match(r'^\d+$', d))
                    missing_fields = 6 - len(published)
                    published = (published + (0,) * missing_fields)[:6]
                    if published[0] < 100:
                        published = (published[0] + 2000,) + published[1:]
                    published = datetime.datetime(*published)
                    published = pytz.utc.localize(published)
                else:
                    published = TZINFO.localize(published)
                if no == max_no or no in crawled_numbers or page == episodes['pageInfo']['lastPage']:
                    stopped = True
                    break
                comic_tuple = no, title, published, href
                logger.info(repr(comic_tuple))
                yield comic_tuple
                crawled_numbers.add(no)
            if stopped:
                break
            page += 1

    def __iter__(self):
        pool = Pool(POOL_SIZE)
        crawled_comics = pool.map_unordered(self._crawl_comic,
                                            self._crawl_list())
        crawled_comics = frozenset(crawled_comics)
        crawled_comics = sorted(crawled_comics, key=lambda c: c.no, reverse=1)
        try:
            start = self.offset
            stop = None if self.limit is None else start + self.limit
            count = 0
            nos = set(comic.no for comic in crawled_comics)
            crawled_comics.sort(key=lambda comic: comic.no, reverse=True)
            for comic in crawled_comics[start:stop]:
                yield comic
                count += 1
            stored_comics = self.session.query(StoredComic) \
                                        .filter_by(title_id=self.title_id) \
                                        .order_by(StoredComic.published_at
                                                             .desc(),
                                                  StoredComic.no.desc())
            step = 30 if self.limit is None else self.limit - count
            offset = 0
            while True:
                resultset = stored_comics.offset(offset).limit(step).all()
                for comic in resultset:
                    if comic.no not in nos:
                        yield comic
                        nos.add(comic.no)
                if self.limit is not None or len(resultset) < step:
                    break
                offset += step
        finally:
            with self.session.begin():
                added_comics = set()
                for comic in crawled_comics:
                    if comic.no not in added_comics:
                        comic.store(self.session, self.title_id)
                        added_comics.add(comic.no)

    def __getitem__(self, index):
        if isinstance(index, (int, long)):
            if index < 0:
                raise ValueError('indices cannot be less than zero')
            for i, comic in enumerate(self):
                if i == index:
                    return comic
                raise IndexError('index out of range')
        elif isinstance(index, slice):
            if index.step is not None:
                raise TypeError('slicing step is not supported')
            limit = index.stop - index.start if index.start else index.stop
            sliced = Title(self.title_id, self.session,
                           index.start or 0, limit,
                           self.cache)
            for attr in self.__slots__:
                if attr.startswith('_') and hasattr(self, attr):
                    setattr(sliced, attr, getattr(self, attr))
            return sliced
        else:
            raise TypeError('indices must be integers')

    def __unicode__(self):
        return unicode(self.title)


class Artist(collections.namedtuple('BaseArtist', 'id name url')):
    """A comic artist. It is a :class:`~collections.namedtuple` so its
    attributes have their tuple position: (:attr:`id`, :attr:`name`,
    :attr:`url`).

    .. attribute:: id

       The artist ID which is used by Naver Comic service.

    .. attribute:: name

       The artist name.

    .. attribute:: url

       An optional Naver Blog URL of the artist.

    """

    @property
    def urls(self):
        """The list of URLs related to the artist. It has one or more URLs."""
        if self.url:
            yield self.url
        yield ARTIST_URL_FORMAT.format(self)

    def __unicode__(self):
        return unicode(self.name)


class BaseComic(object):
    """Base mixin class for :class:`Comic` and :class:`StoredComic`."""

    @property
    def image_url_lines(self):
        """The list of lists that contain image URLs by line."""
        if self.book:
            line = []
            for url in self.image_urls:
                line.append(url)
                if len(line) >= 2:
                    yield line
                    line = []
        else:
            for url in self.image_urls:
                yield [url]

    def __unicode__(self):
        return unicode(self.title)


class Comic(BaseComic):
    """An each comic of series. Interchangeable with :class:`StoredComic`.

    :param url: the url of the comic
    :type url: :class:`basestring`
    :param no: the unique number of the comic used by Naver Comic service
    :type no: :class:`int`, :class:`long`
    :param title: the title of the comic, *not its series name*
    :type title: :class:`basestring`
    :param image_urls: the list of image urls contain the comic
    :type image_urls: iterable object
    :param description: the additional text written by the author
    :type description: :class:`basestring`
    :param published_at: the published time
    :type published_at: :class:`datetime.datetime`

    .. attribute:: url

       The URL of the comic.

    .. attribute:: no

       The unique number of the comic used by Naver Comic service.

    .. attribute:: title

       The title of the comic, *not its series name*.

    .. attribute:: book

       Whether it is book-like.

    .. attribute:: image_urls

       The list of image URLs contain the comic.

    .. attribute:: description

       An additional text written by the author.

    .. attribute:: published_at

       The published :class:`~datetime.datetime`.

    """

    __slots__ = ('url', 'no', 'title', 'book', 'image_urls', 'description',
                 'published_at')

    def __init__(self, url, no, title, book, image_urls, description,
                 published_at):
        l = locals()
        for attr in self.__slots__:
            setattr(self, attr, l[attr])

    def store(self, session, title_id):
        """Stores the comic.

        :param session: an orm session
        :type session: :class:`Session`
        :param title_url: the series title url
        :type title_url: :class:`basestring`

        """
        comic = self.stored_comic
        comic.title_id = title_id
        comic = session.merge(comic)

    @property
    def stored_comic(self):
        """:class:`StoredComic`, its persist version."""
        attrs = dict((attr, getattr(self, attr)) for attr in self.__slots__)
        return StoredComic(**attrs)


class StoredComic(Base, BaseComic):
    """Interchangeable, compatible, but persist version of :class:`Comic`
    object.

    .. attribute:: title_id

       the series title id.

    """

    title_id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    url = sqlalchemy.Column(sqlalchemy.String, unique=True)
    no = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    title = sqlalchemy.Column(sqlalchemy.Unicode, nullable=False)
    book = sqlalchemy.Column(sqlalchemy.Boolean, nullable=False, default=False)
    image_urls = sqlalchemy.Column(sqlalchemy.PickleType, nullable=False)
    description = sqlalchemy.Column(sqlalchemy.UnicodeText, nullable=False)
    published_at = sqlalchemy.Column(sqlalchemy.DateTime(timezone=True),
                                     nullable=False)
    __tablename__ = 'comics'

