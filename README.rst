NaverComicFeed
==============

이 웹 애플리케이션은 `네이버 만화`_ 서비스에서 RSS 피드를 제공하지 않아서 대신
RSS 피드를 제공하기 위해 만들어졌습니다. 메인 서비스는 다음 URL에서 제공되고
있습니다:

http://navercomicfeed.ep.io/

그러나 서비스의 특성상 언제 막히거나 망할지 모르기 때문에, 아예 서비스 소스
코드 자체를 AGPL_ 하에 배포하게 되었습니다. 소스 코드는 Mercurial을 통해
버전 관리되고 있으며, 다음 URL로부터 획득할 수 있습니다:

https://bitbucket.org/dahlia/navercomicfeed

.. _네이버 만화: https://comic.naver.com/
.. _AGPL: http://www.gnu.org/licenses/agpl.html


설치
----

NaverComicFeed는 Python 2.6--2.7 버전을 기준으로 만들어져 있으며, Python 2.5
이하 버전이나 Python 3.x 버전에서는 작동하지 않습니다.

Flask 프레임워크를 사용했으며, 의존하는 라이브러리의 목록은 ``requirements.txt``
파일에 적혀있습니다. pip_ 프로그램을 통해 다음 명령으로 의존하는 모든
라이브러리를 설치 가능합니다::

    $ pip install -r requirements.txt
    $ python setup.py develop

DBMS를 필요로 하는데, PostgreSQL_ 데이터베이스를 가정하고 만들어졌으나, 개발
시에 SQLite_ 위에서도 제대로 동작하는 것을 확인했습니다. 아마 MySQL_ 위에서도
제대로 동작할 것 같지만 확인해본 적은 없습니다.

몇가지 의존 라이브러리가 시스템 전역적으로 설치되는 것이 싫으시다면
virtualenv_ 프로그램을 사용하세요.

.. _pip: http://www.pip-installer.org/
.. _PostgreSQL: http://www.postgresql.org/
.. _SQLite: http://www.sqlite.org/
.. _MySQL: http://www.mysql.com/
.. _virtualenv: http://www.virtualenv.org/


설정
----

설정 파일이 필요합니다. ``default.cfg`` 파일을 복사해서 적당한 이름으로
하나 만드세요. 몇가지 설정 항목이 있는데 적당히 설정해주세요. ``default.cfg``
그대로 사용할 경우 SQLite로 데이터를 저장하고 데이터베이스 파일은 실행 위치에
``db.sqlite`` 파일명으로 저장됩니다.

그 다음에는 데이터베이스에 테이블을 만들어야 합니다. 조금 복잡하지만
다음 명령으로 생성 가능합니다: (설정 파일이 ``mynavercomic.cfg`` 라고 가정) ::

    $ python prepare.py -WB -c mynavercomic.cfg


실행
----

웹 애플리케이션은 WSGI_ 프로토콜을 통해 서버와 통신하게 되어 있으며,
WSGI 엔트리포인트는 ``navercomicfeed.app:app`` 입니다. 자기가 원하는 WSGI
서버 위에서 설치 가능합니다만, WSGI가 무엇인지 모르시는 분들은 그냥 아래에서
소개하는 간단한 방법으로 사용하시면 됩니다.

``mynavercomic.cfg`` 파일이 설정 파일이라고 가정한다면, 다음과 같이 입력하면
웹 서버가 실행됩니다::

    $ NAVERCOMICFEED_CONFIG=mynavercomic.cfg python -m navercomicfeed.app
     * Running on http://127.0.0.1:5000/
     * Restarting with reloader...

이걸 본인 웹 서버와 붙이시려면 프록시 모듈을 쓰시면 됩니다.

.. _WSGI: http://www.python.org/dev/peps/pep-0333/


만든이
------

홍민희가 만들었습니다. 이 프로그램으로 인한 피해는 책임지지 않습니다.

http://dahlia.kr/

