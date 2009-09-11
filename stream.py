"""Lazily-evaluated stream with pipelining via the '>>' operator.

Streams are generalized iterators with a pipelining mechanism defined
in the method __call__(), enabling data-flow programming in Python.

A pipeline usually starts with a generator, then passes through a number
of filters.  Multiple streams can be branched and combined.  Finally,
the output is fed to an accumulator, which can be any function of one
iterable argument.

Generators: seq, gseq, repeatcall, chaincall, anything iterable

Filters: drop, dropwhile, takewhile, map, mapmethod, cut, filter, reduce, apply, generate

Combinators: append, prepend, takei, dropi, tee, flatten

Accumulators: item
	(already in Python: list, sum, max, min, dict, ...)

take() and item[] work similarly, except for notation and the fact that
item[] return a list whereas take() return a stream which can be further
piped to another accumulator.

Values are computed only when an accumulator forces some or all evaluation
(not when the stream are set up).


Example: Grep some lines from file, strip them, then accumulate
----
>>> import re
--> open('log').xreadlines() >> filter(re.compile('[Pp]attern').search) >> mapmethod('strip') >> list


Example: list the first 5 partial sums of the geometric series 1 + 1/2 + 1/4 + ...
----
>>> from operator import add
>>> gseq(0.5) >> reduce(add) >> item[:5]
[1, 1.5, 1.75, 1.875, 1.9375]

Here gseq() generates the geometric series.


Example: random walk in 2D
----
>>> from random import choice
>>> vectoradd = lambda u,v: zip(u, v) >> map(sum) >> list
>>> rw = lambda: repeatcall(choice, [[1,0], [0,1], [-1,0], [0,-1]]) >> reduce(vectoradd, [0, 0])

Here calling choice repeatedly yields the series of unit vectors
representing the directions that the walker takes, then those vectors
are added to get a series of coordinates.

Q: How many step does it take the walker to return to the origin?  Or does
he drift away forever?  Try this a few times!

--> (rw() >> drop(1) >> takewhile(lambda v: v != [0, 0]) >> len) + 1

The first element which is [0, 0] needs to be dropped so that takewhile
does not truncate immediately.

Q: What is the farthest point that he wanders upto the first return?

>>> from functools import partial
>>> vectorlen = lambda v: sum(x**2 for x in v)

--> rw() >> drop(1) >> takewhile(lambda v: v != [0, 0]) >> partial(max, key=vectorlen)

Vectors can be compared lengthwise by the sum of squares of the
components.  The pipe is the same as above otherwise.
"""

#_______________________________________________________________________
#
# NOTE
#_______________________________________________________________________
#
#	* I choose the '>>' operator over the '|' of the UNIX pipe because
# it stands out better in Python code, is less used (e.g. '|' is used
# for set union), and binds more tightly.
#_______________________________________________________________________


__version__ = '0.2'
__author__ = 'Hai-Anh Trinh'
__email__ = 'moc.liamg@hnirt.iah.hna:otliam'[::-1]
__all__ = [
	'Stream',
	'take',
	'takeall',
	'item',
	'takei',
	'drop',
	'dropi',
	'apply',
	'map',
	'mapmethod',
	'cut',
	'filter',
	'reduce',
	'takewhile',
	'dropwhile',
	'generate',
	'tee',
	'prepend',
	'append',
	'flatten',
	'seq',
	'gseq',
	'repeatcall',
	'chaincall'
]

import itertools
import collections

#_______________________________________________________________________
#
# Base class for stream processor
#_____________________________________________________________________

class Stream(object):
	"""A class representing both a stream and a processor.

	The outgoing stream is represented by the attribute 'iterator'.

	The processor is represented by  the method __call__(inpipe), which
	combine iterator self's iterator with inpipe's, producing a new iterator
	representing a new outgoing stream.

	>>> s = Stream(seq(1, 2))
	>>> s >> next
	1
	>>> s >> next
	3
	>>> next(s)
	5
	"""
	__slots__ = 'iterator',

	def __init__(self, iterable=None):
		"""Make a stream object from an iterable"""
		self.iterator = iter(iterable if iterable else [])

	def __iter__(self):
		return self.iterator

	def __next__(self):
		return next(self.iterator)

	def next(self):
		return next(self.iterator)

	def __pipe__(self, inpipe):
		self.iterator = self.__call__(inpipe)
		return self

	def __rshift__(self, outpipe):
		return Stream.pipe(self, outpipe)

	def __rrshift__(self, inpipe):
		return Stream.pipe(inpipe, self)

	@staticmethod
	def pipe(inpipe, outpipe):
		"""Connect inpipe to outpipe by calling outpipe.__pipe__(inpipe)"""
		if hasattr(outpipe, '__pipe__'):
			connect = outpipe.__pipe__
		elif hasattr(outpipe, '__call__'):
			connect = outpipe.__call__
		else:						### no connection mechanism exists
			return outpipe if isinstance(outpipe, Stream) else Stream(outpipe)
		return connect(inpipe)

	def __len__(self):				### this will force all evaluation
		return len(list(self.iterator))

	def __repr__(self):
		return 'Stream(%s)' % repr(self.iterator)


#_______________________________________________________________________
#
# Simple taking and dropping elements
#_______________________________________________________________________


negative = lambda x: x and x<0		### since None < 0 == True


class take(Stream):
	"""Force some or all evaluation and use slice-like arguments to select elements.
	Return a Stream.
	
	>>> seq(1, 2) >> take(10)
	Stream([1, 3, 5, 7, 9, 11, 13, 15, 17, 19])

	>>> gseq(2) >> take(0, 16, 2)
	Stream([1, 4, 16, 64, 256, 1024, 4096, 16384])
	"""
	__slots__ = 'slice', 'cache'

	def __init__(self, *args):
		self.iterator = iter([])
		self.slice = slice(*args)
		self.cache = []

	def __call__(self, inpipe):
		if negative(self.slice.stop) or negative(self.slice.start) \
		or not (self.slice.start or self.slice.stop) \
		or (not self.slice.start and negative(self.slice.step)) \
		or (not self.slice.stop and not negative(self.slice.step)):
			self.cache = list(inpipe)		## force all evaluation 	##
		else:							## force some evaluation ##
			if negative(self.slice.step):
				stop = self.slice.start
			else:
				stop = self.slice.stop
			i = iter(inpipe)
			try:
				self.cache =  [next(i) for _ in xrange(stop)]
			except StopIteration:
				pass
		self.cache = self.cache[self.slice]
		return iter(self.cache)

	def __len__(self):
		return len(self.cache)

	def __repr__(self):
		return 'Stream(%s)' % repr(self.cache)

takeall = take(None)


class itemgetter(take):
	"""
	Implement Python slice notation for take. Return a list.

	>>> xrange(20) >> item[10]
	10

	>>> xrange(20) >> item[::-2]
	[19, 17, 15, 13, 11, 9, 7, 5, 3, 1]

	>>> xrange(20) >> item[5::2]
	[5, 7, 9, 11, 13, 15, 17, 19]
	"""
	__slots__ = 'get1'

	def __init__(self):
		self.iterator = iter([])
		self.get1 = False

	@classmethod
	def __getitem__(cls, sliceobj):
		getter = cls()
		if type(sliceobj) is type(1):
			getter.get1 = True
			if sliceobj == -1:
				sliceobj = None
			else:
				sliceobj += 1
			getter.slice = slice(sliceobj)
		else:
			getter.slice = sliceobj
		return getter

	def __pipe__(self, inpipe):
		super(itemgetter, self).__call__(inpipe)
		if self.get1:
			return self.cache[-1]
		else:
			return self.cache

	def __repr__(self):
		return '<itemgetter at %s>' % hex(id(self))

item = itemgetter()


class takei(Stream):
	"""Select elements of the incoming stream by a stream of indexes.

	>>> seq() >> takei(xrange(2,43,4)) >> list
	[2, 6, 10, 14, 18, 22, 26, 30, 34, 38, 42]

	>>> xrange(15) >> takei([3, -2, 7, 7]) >> list
	[3, 7]
	"""
	__slots__ = 'indexiter'

	def __init__(self, indices):
		"""indexes should be non-negative integers in monotonically
		increasing order (bad values won't yield)
		"""
		self.iterator = iter([])
		self.indexiter = iter(indices)

	def __call__(self, inpipe):
		def genfunc():
			i = iter(inpipe)
			old_idx = -1
			idx = next(self.indexiter)			# next value to yield
			counter = seq()
			while 1:
				c = next(counter)
				elem = next(i)
				while idx <= old_idx:		# ignore bad values
					idx = next(self.indexiter)
				if c == idx:
					yield elem
					old_idx = idx
					idx = next(self.indexiter)
		return genfunc()


class drop(Stream):
	"""Drop the first n elements of the incoming stream

	>>> seq(0, 2) >> drop(1) >> take(5)
	Stream([2, 4, 6, 8, 10])
	"""
	__slots__ = 'n'
	
	def __init__(self, n):
		"""n: the number of elements to be dropped"""
		self.iterator = iter([])
		self.n = n

	def __call__(self, inpipe):
		i = iter(inpipe)
		collections.deque(itertools.islice(i, self.n), maxlen=0)
		return i


class dropi(Stream):
	"""Drop elements of the incoming stream by indexes.

	>>> seq() >> dropi(seq(0,3)) >> item[:10]
	[1, 2, 4, 5, 7, 8, 10, 11, 13, 14]

	>>> xrange(11) >> dropi([-2, 3, 7, 7, 6, 9]) >> list
	[0, 1, 2, 4, 5, 6, 8, 10]

	>>> xrange(11) >> dropi([]) >> list
	[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
	"""
	__slot__ = 'indexiter'

	def __init__(self, indices):
		"""indexes: a stream of the indexs of element to be selected.

		indexes should be non-negative integers in monotonically
		increasing order (bad values won't be discarded)
		"""
		self.iterator = iter([])
		self.indexiter = iter(indices)

	def __call__(self, inpipe):
		def genfunc():
			i = iter(inpipe)
			counter = seq()
			def try_next_idx():
				## so that the stream keeps going 
				## after the discard iterator is exhausted
				try:
					return next(self.indexiter), False
				except StopIteration:		
					return -1, True
			old_idx = -1
			idx, exhausted = try_next_idx()			# next value to discard
			while 1:
				c =next(counter)
				elem = next(i)
				while not exhausted and idx <= old_idx:	# ignore bad values
					idx, exhausted = try_next_idx()	
				if c != idx:
					yield elem
				elif not exhausted:
					old_idx = idx
					idx, exhausted = try_next_idx()
		return genfunc()


#_______________________________________________________________________
#
# Functional processing
#_______________________________________________________________________


class FunctionFilter(Stream):
	"""Base class for stream filter based on a function"""

	__slots__ = 'function'

	def __init__(self, function):
		self.iterator = iter([])
		self.function = function


class apply(FunctionFilter):
	"""Invoke a function using each stream element as a list of arguments, 
	a la itertools.starmap.
	"""
	def __call__(self, inpipe):
		return itertools.starmap(self.function, inpipe)


class map(FunctionFilter):
	def __call__(self, inpipe):
		return itertools.imap(self.function, inpipe)


class mapmethod(map):
	"""Call method m(*args, **kwargs) on the each object that comes out of the input pipe.

	>>> ['foo bar 1', 'foo bar 2'] >> mapmethod('split') >> list
	[['foo', 'bar', '1'], ['foo', 'bar', '2']]
	"""
	def __init__(self, m, *args, **kwargs):
		f = lambda obj: getattr(obj, m)(*args, **kwargs)
		super(map, self).__init__(f)


class itemcutter(mapmethod):
	"""A mapmethod on '__itemgetter__' with slice notation.

	>>> [[1, 2, 3], [4, 5, 6]] >> cut[::2] >> list
	[[1, 3], [4, 6]]
	"""

	def __init__(self, *args):
		super(itemcutter, self).__init__('__getitem__', *args)

	@classmethod
	def __getitem__(cls, args):
		return cls(args)

	def __repr__(self):
		return '<cutter at %s>' % hex(id(self))

cut = itemcutter()


class filter(FunctionFilter):
	"""
	>>> even = lambda x: x%2 == 0
	>>> xrange(1, 40, 3) >> filter(even) >> list
	[4, 10, 16, 22, 28, 34]
	"""
	def __call__(self, inpipe):
		return itertools.ifilter(self.function, inpipe)


class takewhile(FunctionFilter):
	def __call__(self, inpipe):
		return itertools.takewhile(self.function, inpipe)


class dropwhile(FunctionFilter):
	def __call__(self, inpipe):
		return itertools.dropwhile(self.function, inpipe)


class reduce(FunctionFilter):
	"""Haskell's scanl.

	>>> from operator import add
	>>> gseq(0.5) >> reduce(add) >> item[:5]
	[1, 1.5, 1.75, 1.875, 1.9375]
	"""
	def __init__(self, function, initval=None):
		self.iterator = iter([])
		self.function = function
		self.initval = initval

	def __call__(self, inpipe):
		def genfunc():
			i = iter(inpipe)
			if self.initval:
				accumulated = self.initval
			else:
				accumulated = next(i)
			while 1:
				yield accumulated
				val = next(i)
				accumulated = self.function(accumulated, val)
		return genfunc()


class generate(Stream):
	"""Eval an generator expression where {0} indicates the input stream"""
	__slots__ = 'expr'

	def __init__(self, expr):
		self.expr = expr
		self.iterator = iter([])

	def __call__(self, inpipe):
		return eval( '(' + self.expr.format('inpipe') + ')' )


#_______________________________________________________________________
#
# Stream combinators
#_____________________________________________________________________


class prepend(Stream):
	"""Prepend at the beginning of a stream.

	>>> seq(7, 7) >> prepend(xrange(0, 10, 2)) >> item[:10]
	[0, 2, 4, 6, 8, 7, 14, 21, 28, 35]
	"""
	def __call__(self, inpipe):
		"""Prepend at the beginning of inpipe"""
		return itertools.chain(self.iterator, inpipe)


class append(Stream):
	"""Append to the end of a stream (it had better terminate!)

	>>> xrange(1, 20, 7) >> append(xrange(1, 10, 3)) >> append('foo') >> list
	[1, 8, 15, 1, 4, 7, 'f', 'o', 'o']
	"""
	def __call__(self, inpipe):
		"""Append to the end of inpipe"""
		return itertools.chain(inpipe, self.iterator)


class tee(Stream):
	"""Make a branch from a stream.

	>>> foo = filter(lambda x: x%3==0)
	>>> bar = seq(0, 2) >> tee(foo)
	>>> bar >> item[:5]
	[0, 2, 4, 6, 8]
	>>> foo >> item[:5]
	[0, 6, 12, 18, 24]
	"""
	__slots__ = 'streamobj',

	def __init__(self, streamobj):
		self.streamobj = streamobj
		self.iterator = iter([])

	def __pipe__(self, inpipe):
		"""Make a branch of inpipe to pipe to self.streamobj"""
		branch1, branch2 = itertools.tee(inpipe)
		Stream.pipe(branch1, self.streamobj)
		if isinstance(inpipe, Stream):
			inpipe.iterator = branch2
			return inpipe
		else:
			return Stream(branch2)

#_______________________________________________________________________
#
# Nested streams processing
#_______________________________________________________________________


class flattener(Stream):
	"""Flatten a nested stream of arbitrary depth

	>>> (xrange(i) for i in seq(step=3)) >> flatten >> item[:18]
	[0, 1, 2, 0, 1, 2, 3, 4, 5, 0, 1, 2, 3, 4, 5, 6, 7, 8]
	"""
	@staticmethod
	def __call__(inpipe):
		def flatten():
			## Maintain a LIFO stack of iterators
			stack = []
			i = iter(inpipe)
			while True:
				try:
					e = next(i)
					if hasattr(e, "__iter__") and not isinstance(e, basestring):
						stack.append(i)
						i = iter(e)
					else:
						yield e
				except StopIteration:
					try:
						i = stack.pop()
					except IndexError:
						break
		return flatten()

	def __repr__(self):
		return '<flattener at %s>' % hex(id(self))

flatten = flattener()


#_______________________________________________________________________
#
# Useful ultilities
#_____________________________________________________________________


def seq(start=0, step=1):
	"""An arithmetic sequence generator.  Works with any type with + defined.

	>>> seq(1, 0.25) >> item[:10]
	[1, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.25]
	"""
	def seq(a, d):
		while 1:
			yield a
			a += d
	return seq(start, step)

def gseq(*args):
	"""A geometric sequence generator.  Works with any type with * defined.

	>>> from decimal import Decimal
	>>> gseq(Decimal('.2')) >> item[:4]
	[1, Decimal('0.2'), Decimal('0.04'), Decimal('0.008')]
	"""
	def gseq(a, r):
		while 1:
			yield a
			a *= r
	if len(args) == 1:
		return gseq(1, args[0])
	elif len(args) == 2:
		return gseq(args[0], args[1])
	else:
		raise TypeError('gseq expects 1 or 2 arguments, got %s' % len(args))

def repeatcall(func, *args):
	"""Repeatedly call func(*args) and yield the result.

	Useful when func(*args) returns different results, esp. randomly.
	"""
	return itertools.starmap(func, itertools.repeat(args))

def chaincall(func, initval):
	"""Yield func(initval), func(func(initval)), etc."""
	x = initval
	while 1:
		yield x
		x = func(x)


if __name__ == "__main__":
	import doctest
	doctest.testmod()
