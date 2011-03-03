""":mod:`navercomicfeed.pool` --- Naive worker pool implementation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Worker pool is a pattern so commonly showed/used in NaverComic that
this module provides general worker pool implementation.

There's two methods for :class:`Pool`: :meth:`~Pool.map()` and
:meth:`Pool.map_unordered()`. They are drop-in replacements of built-in
:func:`map()` function::

    pool = Pool(5)
    pool.map(very_slow_function, xrange(100))

"""
import itertools
import threading


class Pool(object):
    """A very simple and naive implementation of worker pool.

    :param workers: the number of workers
    :type workers: :class:`int`, :class:`long`

    """

    __slots__ = 'workers',

    def __init__(self, workers):
        if not isinstance(workers, (int, long)):
            raise TypeError('workers must be an integer, not ' + repr(workers))
        self.workers = workers

    def map(self, function, *iterables):
        """Its behavior is equivalent to built-in function :func:`map()`, but
        it internally maps iterable objects in parellel.

        :param function: a mapping function
        :type function: callable object
        :param \*iterables: iterable objects to map
        :returns: a mapped iterable object
        :rtype: iterable object

        """
        iterable = enumerate(itertools.izip_longest(*iterables))
        map_func = lambda (i, args): (i, function(*args))
        result = self.map_unordered(map_func, iterable)
        result.sort(key=lambda (i, retval): i)
        for i, retval in result:
            yield retval

    def map_unordered(self, function, *iterables):
        """The same as :meth:`map()`, but it doesn't gurantee that the order
        of its result follows its input ``iterables``.

        :param function: a mapping function
        :type function: callable object
        :param \*iterables: iterable objects to map
        :returns: a mapped list
        :rtype: :class:`list`

        """
        workers = []
        cond = threading.Condition()
        result = []
        zipped = itertools.izip_longest(*iterables)
        for values in zipped:
            if sum(w.is_alive() for w in workers) > self.workers:
                with cond:
                    cond.wait()
            worker = threading.Thread(target=self.append_result,
                                      args=(cond, result, function, values))
            worker.start()
            workers.append(worker)
        for worker in workers:
            worker.join()
        return result

    def append_result(self, condition, result, function, args):
        retval = function(*args)
        result.append(retval)
        with condition:
            condition.notify()

