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

.. data:: TITLE_XPATH
.. data:: DESCRIPTION_XPATH
.. data:: ARTIST_URL_FORMAT
.. data:: ARTIST_PATTERN
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
import threading
import urlparse
import urllib2
import datetime
import pytz
import lxml.etree
import lxml.html
import sqlalchemy
import sqlalchemy.orm
import sqlalchemy.ext.declarative
import sqlalchemy.sql.functions


POOL_SIZE = 20
TZINFO = pytz.timezone('Asia/Seoul')
TITLE_XPATH = lxml.etree.XPath('//*[@class="comicinfo"]//h2/text()')
DESCRIPTION_XPATH = lxml.etree.XPath('//*[@class="comicinfo"]'
                                     '/*[@class="detail"]/p/text()')
ARTIST_URL_FORMAT = 'http://comic.naver.com/artistTitle.nhn?artistId={0.id}'
ARTIST_LIST_PATTERN = re.compile(ur'''
    var \s* artistData \s* = \s* \[ \s* ( .+? ) \s* \] \s* ; \s* var
''', re.VERBOSE | re.DOTALL)
ARTIST_PATTERN = re.compile(ur'''
    { \s* ['"]? artistId ['"]? \s* : \s* (?P<id> \d+ ) \s* ,
      \s* ['"]? nickname ['"]? \s* : \s* ['"] (?P<name> .*? ) ['"] \s*
      (?: , \s* ['"]? blogUrl ['"]? \s* : \s* ['"] (?P<url> .*? ) ['"] \s* )?
    } \s* ,?
''', re.VERBOSE)
COMIC_XPATH = lxml.etree.XPath('//*[@id="content"]/table[@class="viewList"]'
                               '//tr/td[@class="title"]/..')
COMIC_TITLE_XPATH = lxml.etree.XPath('.//td[@class="title"]/a/text()')
COMIC_URL_XPATH = lxml.etree.XPath('.//td[@class="title"]/a/@href')
COMIC_PUBLISHED_AT_XPATH = lxml.etree.XPath('.//td[@class="num"]/text()')
COMIC_IMAGE_URLS_XPATH = lxml.etree.XPath('//*[@id="content"]'
                                          '//*[@class="wt_viewer"]/img/@src')
COMIC_DESCRIPTION_XPATH = lxml.etree.XPath('//*[@id="content"]'
                                           '//*[@class="writer_info"]/p/text()')

Session = sqlalchemy.orm.sessionmaker(autocommit=True)
Session = sqlalchemy.orm.scoped_session(Session)
Base = sqlalchemy.ext.declarative.declarative_base()


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

    __slots__ = ('url', 'session', 'offset', 'limit', '_title', '_description',
                 '_artists', '_list_html', '_list_page')

    def __init__(self, url, session, offset=0, limit=None):
        self.url = url
        self.session = session
        self.offset = offset
        self.limit = limit

    def _get_list_html(self, page=None, pair=False):
        p = page or 1
        params = self.url, ('&' if '?' in self.url else '?'), p
        url = '{0}{1}page={2}'.format(*params)
        if not hasattr(self, '_list_html') or page and self._list_page != page:
            self._list_html = lxml.html.parse(url)
            self._list_page = page
        if pair:
            return self._list_html, url
        return self._list_html

    @property
    def title(self):
        """The title string."""
        if not hasattr(self, '_title'):
            self._title = TITLE_XPATH(self._get_list_html())[0]
        return self._title

    @property
    def description(self):
        """The description string."""
        if not hasattr(self, '_description'):
            self._title = TITLE_XPATH(self._get_list_html())[0]
        return self._title

    def _fetch_artists(self, html):
        script = html.xpath('//script[contains(text(), "artistData")]'
                            '/text()')
        for s in script:
            lst = ARTIST_LIST_PATTERN.search(s)
            if not lst:
                continue
            lst = lst.group(1)
            self._artists = [Artist(int(m.group('id')), m.group('name'),
                                    m.group('url') or None)
                             for m in ARTIST_PATTERN.finditer(lst)]
            if self._artists:
                break

    @property
    def artists(self):
        """The :class:`Artist` list."""
        if not hasattr(self, '_artists'):
            self._artists = []
            self._fetch_artists(self._get_list_html())
        return self._artists

    def _crawl_comic(self, lock, cond_pool_buffer, resultset, no, title,
                     published, comic_url):
        f = urllib2.urlopen(comic_url)
        comic_html = lxml.html.parse(f)
        f.close()
        if len(resultset) < 1:
            self._fetch_artists(comic_html)
        image_urls = COMIC_IMAGE_URLS_XPATH(comic_html)
        description = u"\n\n".join(COMIC_DESCRIPTION_XPATH(comic_html))
        comic = Comic(comic_url, no, title, image_urls,
                      description, published)
        if lock is None:
            resultset.append(comic)
        else:
            with lock:
                resultset.append(comic)
        if cond_pool_buffer is not None:
            with cond_pool_buffer:
                cond_pool_buffer.notify()

    def __iter__(self):
        max = sqlalchemy.sql.functions.max
        max_no, = self.session.query(max(StoredComic.no)) \
                              .filter_by(title_url=self.url) \
                              .first()
        page = 1
        no_re = re.compile(r'[?&]no=(\d+)(&|$)')
        stopped = False
        crawled_comics = []
        lock = threading.Lock()
        cond_pool_buffer = threading.Condition()
        workers = []
        while True:
            html, title_url = self._get_list_html(page, pair=True)
            for tr in COMIC_XPATH(html):
                title = COMIC_TITLE_XPATH(tr)[0].strip()
                href = COMIC_URL_XPATH(tr)[0]
                no = int(no_re.search(href).group(1))
                published = COMIC_PUBLISHED_AT_XPATH(tr)[0]
                try:
                    published = datetime.datetime.strptime(
                        published,
                        '%a %b %d %H:%M:%S %Z %Y'
                    )
                except ValueError:
                    published = [int(d)
                                 for d in re.split(r'\D+', published.strip())
                                 if re.match(r'^\d+$', d)]
                    published = (published + (0,) * 6 - len(published))[:6]
                    published = datetime.datetime(*published)
                    published = pytz.utc.localize(published)
                else:
                    published = TZINFO.localize(published)
                if no == max_no or any(c.no == no for c in crawled_comics):
                    stopped = True
                    break
                comic_url = urlparse.urljoin(title_url, href)
                if POOL_SIZE < 2:
                    self._crawl_comic(None, None, crawled_comics, no, title,
                                      published, comic_url)
                else:
                    if sum(1 for w in workers if w.is_alive()) >= POOL_SIZE:
                        with cond_pool_buffer:
                            cond_pool_buffer.wait()
                        workers = [w for w in workers if w.is_alive()]
                    worker = threading.Thread(target=self._crawl_comic,
                                              args=(lock, cond_pool_buffer,
                                                    crawled_comics,
                                                    no, title, published,
                                                    comic_url))
                    worker.start()
                    workers.append(worker)
            if stopped:
                break
            page += 1
        for worker in workers:
            worker.join()
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
                                        .filter_by(title_url=self.url) \
                                        .order_by(StoredComic.no.desc())
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
                        comic.store(self.session, self.url)
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
            sliced = Title(self.url, self.session, index.start or 0, limit)
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


class Comic(object):
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

    .. attribute:: image_urls

       The list of image URLs contain the comic.

    .. attribute:: description

       An additional text written by the author.

    .. attribute:: published_at

       The published :class:`~datetime.datetime`.

    """

    __slots__ = ('url', 'no', 'title', 'image_urls', 'description',
                 'published_at')

    def __init__(self, url, no, title, image_urls, description, published_at):
        l = locals()
        for attr in self.__slots__:
            setattr(self, attr, l[attr])

    def store(self, session, title_url):
        """Stores the comic.

        :param session: an orm session
        :type session: :class:`Session`
        :param title_url: the series title url
        :type title_url: :class:`basestring`

        """
        comic = self.stored_comic
        comic.title_url = title_url
        session.add(comic)

    @property
    def stored_comic(self):
        """:class:`StoredComic`, its persist version."""
        attrs = dict((attr, getattr(self, attr)) for attr in self.__slots__)
        return StoredComic(**attrs)

    def __unicode__(self):
        return unicode(self.title)


class StoredComic(Base):
    """Interchangeable, compatible, but persist version of :class:`Comic`
    object.

    .. attribute:: title_url

       the series title URL.

    """

    title_url = sqlalchemy.Column(sqlalchemy.String, primary_key=True)
    url = sqlalchemy.Column(sqlalchemy.String, unique=True)
    no = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    title = sqlalchemy.Column(sqlalchemy.Unicode, nullable=False)
    image_urls = sqlalchemy.Column(sqlalchemy.PickleType, nullable=False)
    description = sqlalchemy.Column(sqlalchemy.UnicodeText, nullable=False)
    published_at = sqlalchemy.Column(sqlalchemy.DateTime(timezone=True),
                                     nullable=False)
    __tablename__ = 'comics'

    def __unicode__(self):
        return unicode(self.title)

