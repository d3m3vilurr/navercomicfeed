#!/usr/bin/env python
"""jfile:`prepare.py`
~~~~~~~~~~~~~~~~~~~~~

"""
import sys
import os
import sqlalchemy
import navercomicfeed.app
import navercomicfeed.comic


def comics():
    for title_id, title in navercomicfeed.app.webtoon_comics():
        yield 'webtoon', title_id, title
    for title_id, title in navercomicfeed.app.bestchallenge_comics():
        yield 'bestchallenge', title_id, title


def titles(session):
    for type, title_id, title_str in comics():
        url = navercomicfeed.app.URL_TYPES[type].format(title_id)
        title = navercomicfeed.comic.Title(url, session,
                                           cache=navercomicfeed.app.cache)
        yield title_str, title


def main(encoding=None):
    database_url = navercomicfeed.app.app.config['DATABASE']
    engine = sqlalchemy.create_engine(database_url)
    navercomicfeed.comic.Base.metadata.create_all(engine)
    navercomicfeed.comic.Session.configure(bind=engine)
    session = navercomicfeed.comic.Session()
    for title_str, title in titles(session):
        print '[{0}]'.format(title_str.encode(encoding)), title.url
        for comic in title:
            print '{0}:'.format(comic.title.encode(encoding)), comic.url


if __name__ == '__main__':
    if len(sys.argv) < 2:
        if 'NAVERCOMICFEED_CONFIG' not in os.environ:
            print>>sys.stderr, 'usage:', sys.argv[0], 'config'
            raise SystemExit
    else:
        navercomicfeed.app.app.config.from_pyfile(os.path.abspath(sys.argv[1]))
    try:
        _, encoding = os.environ.get('LANG', 'en_US.ascii').split('.', 1)
    except ValueError:
        encoding = 'utf-8'
    main(encoding=encoding)

