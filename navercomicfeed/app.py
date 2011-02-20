""":mod:`navercomicfeed.app`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

"""
from flask import *
from flaskext.cache import Cache
import lxml.html
import werkzeug.urls
from navercomicfeed.comic import *


WEBTOON_LIST_URL = 'http://comic.naver.com/webtoon/creation.nhn?view=list'
URL_TYPES = {
    'webtoon': 'http://comic.naver.com/webtoon/list.nhn?titleId={0}',
    'challenge': 'http://comic.naver.com/challenge/list.nhn?titleId={0}',
    'bestchallenge': 'http://comic.naver.com/bestChallenge/list.nhn?titleId={0}'
}


app = Flask(__name__)
cache = Cache(app)


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


@app.route('/<any(webtoon,bestchallenge,challenge):type>/<int:title_id>.xml')
@cache.cached(timeout=120)
def feed(type, title_id):
    from sqlalchemy import create_engine
    engine = create_engine('sqlite:///db.sqlite')
    Base.metadata.create_all(engine)
    Session.configure(bind=engine)
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
    xml = render_template('feed.xml', title=title)
    return Response(response=xml, content_type='application/atom+xml')


if __name__ == '__main__':
    app.run(debug=True)

