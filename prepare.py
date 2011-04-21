#!/usr/bin/env python
"""jfile:`prepare.py`
~~~~~~~~~~~~~~~~~~~~~

"""
import os
import sys
import optparse
import itertools
import sqlalchemy
import navercomicfeed.app
import navercomicfeed.comic


def comics(type, comics):
    for title_id, title in comics:
        yield type, title_id, title


def titles(comics, session):
    for type, title_id, title_str in comics:
        url = navercomicfeed.app.URL_TYPES[type].format(title_id)
        title = navercomicfeed.comic.Title(url, session,
                                           cache=navercomicfeed.app.cache)
        yield title_str, title


def setup():
    database_url = navercomicfeed.app.app.config['DATABASE']
    engine = sqlalchemy.create_engine(database_url)
    navercomicfeed.comic.Base.metadata.create_all(engine)
    navercomicfeed.comic.Session.configure(bind=engine)
    return navercomicfeed.comic.Session()


def crawl_urls(urls, encoding=None):
    session = setup()
    encoding = encoding or sys.getdefaultencoding()
    for url in urls:
        title = navercomicfeed.comic.Title(url, session,
                                           cache=navercomicfeed.app.cache)
        print url
        for comic in title:
            print '{0}:'.format(comic.title.encode(encoding)), comic.url


def crawl_titles(comics, encoding=None):
    session = setup()
    encoding = encoding or sys.getdefaultencoding()
    for title_str, title in titles(comics, session):
        print '[{0}]'.format(title_str.encode(encoding)), title.url
        for comic in title:
            print '{0}:'.format(comic.title.encode(encoding)), comic.url


def main():
    try:
        _, encoding = os.environ.get('LANG', 'en_US.ascii').split('.', 1)
    except ValueError:
        encoding = 'ascii'
    parser = optparse.OptionParser(usage='usage: %prog [options] [urls...]')
    parser.add_option('-c', '--config', help='configuration file')
    parser.add_option('-e', '--encoding', default=encoding,
                      help='output encoding [%default]')
    parser.add_option('-W', '--no-webtoon', action='store_false',
                      dest='webtoon', default=True,
                      help="don't crawl webtoons")
    parser.add_option('-B', '--no-bestchallenge', action='store_false',
                      dest='bestchallenge', default=True,
                      help="don't crawl webtoons")
    options, args = parser.parse_args()
    if not options.config:
        if 'NAVERCOMICFEED_CONFIG' not in os.environ:
            parser.error('-c/--config option is required')
    else:
        config = os.path.abspath(options.config)
        navercomicfeed.app.app.config.from_pyfile(config)
    if args and not (options.webtoon and options.bestchallenge):
        parser.error('-W/--no-webtoon and -B/--no-bestchallenge options are '
                     'meaningless for specific urls')
    comic_list = []
    if options.webtoon:
        comic_list = comics('webtoon', navercomicfeed.app.webtoon_comics())
    if options.bestchallenge:
        lst = comics('bestchallenge',
                     navercomicfeed.app.bestchallenge_comics())
        comic_list = itertools.chain(comic_list, lst) if comic_list else lst
    if args:
        crawl_urls(args, encoding=options.encoding)
    else:
        crawl_titles(comic_list, encoding=options.encoding)


if __name__ == '__main__':
    main()
