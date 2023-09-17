try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


setup(name='NaverComicFeed',
      version='0.1',
      url='https://bitbucket.org/dahlia/navercomicfeed',
      author='Hong Minhee',
      author_email='minhee' '@' 'dahlia.kr',
      packages=['navercomicfeed'],
      package_dir={'navercomicfeed': 'navercomicfeed'},
      install_requires=['lxml', 'SQLAlchemy', 'pytz',
                        'Flask==1.0', 'Flask-Cache',
                        'Werkzeug==0.16'],
      license='LGPL v3')

