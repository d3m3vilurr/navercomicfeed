""":mod:`futureutils` --- Iterators implementing `futures and promises`_
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. codeauthor:: Hong Minhee <minhee@dahlia.kr>

This module provides several trivial wrappers of iterable object that
makes iterators running in parallel easily and simply. Why its name is
:mod:`futureutils` is that it introduces the concept of `futures and promises`_
into Python iterators and generators.

It works well on Python 2.5+ --- CPython 2.5+, PyPy 1.4+.

.. _futures and promises: http://en.wikipedia.org/wiki/Futures_and_promises

.. data:: DEFAULT_BUFFER_SIZE

   Promised iterators have their own buffer queue internally, and every queue
   has their maximum size. It intends to avoid wasting memory unlimitedly in
   case of infinite iterators.

   This constant is a default size of a queue.

.. data:: SIGNAL_YIELD
.. data:: SIGNAL_RAISE
.. data:: SIGNAL_RETURN
.. data:: SIGNAL_CONTINUE

   The internal-use only flag constants.

"""
import sys
import functools
import threading
import Queue

__author__ = 'Hong Minhee <minhee@dahlia.kr>'
__license__ = 'MIT License'
__version__ = '1.1'

DEFAULT_BUFFER_SIZE = 100
SIGNAL_YIELD = 0
SIGNAL_RAISE = 1
SIGNAL_BREAK = 2
SIGNAL_CONTINUE = 3


def promise(iterable, buffer_size=DEFAULT_BUFFER_SIZE):
    """Promises the passed ``iterable`` object and returns its future
    iterator.

    .. sourcecode:: pycon

       >>> import time, datetime
       >>> def myiter():
       ...     for x in xrange(5):
       ...         yield x
       ...         time.sleep(0.5)
       ...
       >>> it = promise(myiter())
       >>> time.sleep(2)
       >>> start = datetime.datetime.now()
       >>> list(it)
       [0, 1, 2, 3, 4]
       >>> delta = datetime.datetime.now() - start
       >>> delta.seconds
       0
       >>> delta.microseconds > 500000
       True

    It could be used for simple parallelization of IO-bound iterable objects.

    It propagates an inner exception during iteration also as well as a normal
    iterator:

    .. sourcecode:: pycon

       >>> def pooriter():
       ...     yield 1
       ...     raise Exception('future error')
       ...
       >>> it = promise(pooriter())
       >>> it.next()
       1
       >>> it.next()
       Traceback (most recent call last):
         ...
       Exception: future error

    It can deal with infinite iterators as well also:

    .. sourcecode:: pycon

       >>> import itertools
       >>> it = promise(itertools.cycle('Hong Minhee '))
       >>> ''.join(itertools.islice(it, 23))
       'Hong Minhee Hong Minhee'

    Every future iterator has its own buffer queue that stores iterator's
    result internally, and every queue has their maximum size. It intends
    to avoid wasting memory unlimitedly in case of infinite iterators.
    You can tune the queue buffer size through ``buffer_size`` option.

       >>> import itertools
       >>> def infloop():
       ...     i = 0
       ...     while True:
       ...         print i
       ...         yield i
       ...         i += 1
       ...
       >>> list(itertools.islice(promise(infloop(), buffer_size=5), 5)
       ... )  # doctest: +ELLIPSIS
       0
       1
       2
       3
       4
       ...
       [0, 1, 2, 3, 4]

    :param iterable: an iterable object to promise
    :type iterable: iterable object
    :param buffer_size: it has its own buffer queue that stores iterator's
                        result internally, and every queue has their maximum
                        size. it intends to avoid wasting too many memory.
                        by default it follows the constant
                        :const:`~futureutils.DEFAULT_BUFFER_SIZE`
    :type buffer_size: :func:`int`, :func:`long`
    :returns: a promised future iterator
    :rtype: iterable object

    .. seealso:: Decorator :func:`future_generator()`

    """
    try:
        iterator = iter(iterable)
    except TypeError:
        raise TypeError('expected an iterable object, but ' + repr(iterable) +
                        'is not iterable')
    if not isinstance(buffer_size, (int, long)):
        raise TypeError('buffer size must be an integer, not ' +
                        repr(buffer_size))
    elif buffer_size < 0:
        raise ValueError('buffer size cannot be zero or negative')
    result = Queue.Queue()
    def iterate(iterator, result, buffer_size):
        stopped = False
        try:
            for el in iterator:
                result.put((SIGNAL_YIELD, el))
                if result.qsize() >= buffer_size:
                    result.put((SIGNAL_CONTINUE,))
                    stopped = True
                    break
        except Exception, e:
            result.put((SIGNAL_RAISE, e, sys.exc_info()[2]))
        else:
            result.put((SIGNAL_BREAK,))
        finally:
            if not stopped:
                result.task_done()
    thread = [None]
    def start_thread():
        t = threading.Thread(target=iterate,
                             args=(iterator, result, buffer_size))
        t.start()
        thread[0] = t
    start_thread()
    def iterator():
        while True:
            signal = result.get()
            if signal[0] == SIGNAL_YIELD:
                yield signal[1]
            elif signal[0] == SIGNAL_RAISE:
                raise signal[1], None, signal[2]
            elif signal[0] == SIGNAL_BREAK:
                break
            elif signal[0] == SIGNAL_CONTINUE:
                thread[0].join()
                start_thread()
        thread[0].join()
    return iterator()


def future_generator(function):
    """The decorator that makes the result of decorated generator ``function``
    to be promised and return a future iterator.

    It's a simple decorator wrapper of :func:`promise()` for generator
    functions.

    .. sourcecode:: pycon

       >>> import time, datetime
       >>> @future_generator
       ... def mygenerator():
       ...     for x in xrange(5):
       ...         yield x
       ...         time.sleep(0.5)
       ...
       >>> it = mygenerator()
       >>> time.sleep(2)
       >>> start = datetime.datetime.now()
       >>> list(it)
       [0, 1, 2, 3, 4]
       >>> delta = datetime.datetime.now() - start
       >>> delta.seconds
       0
       >>> delta.microseconds > 500000
       True

    :param function: a generator function to make to future generator
    :type function: callable object
    :returns: a future generator function
    :rtype: callable object

    .. seealso:: Function :func:`promise()`

    """
    @functools.wraps(function)
    def promised_generator(*args, **kwargs):
        return promise(function(*args, **kwargs))
    return promised_generator


if __name__ == '__main__':
    import doctest
    doctest.testmod()

