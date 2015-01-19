
from monotonic import monotonic


class Timer(object):
	"""A stateful timer object that can be started, get the current time, and marked (see mark()).
	Cannot be stopped or reset - just make a new one.
	Uses monotonic time.
	"""
	start_time = None

	def __init__(self, start=False):
		"""Optionally start timer immediately"""
		if start:
			self.start()

	def start(self):
		"""Begin the timer"""
		self.start_time = monotonic()
		self.mark_time = self.start_time

	def get(self):
		"""Return the time elapsed since start"""
		if self.start_time is None:
			raise ValueError("Timer is not started")
		return monotonic() - self.start_time

	def mark(self, peek=False):
		"""Marks the current time, and returns the elapsed time since the last mark.
		If peek=True, return elapsed time without changing the mark."""
		if self.start_time is None:
			raise ValueError("Timer is not started")
		now = monotonic()
		elapsed = now - self.mark_time
		if not peek:
			self.mark_time = now
		return elapsed


def parse_time(data):
	"""Recognise [[H:]M:]S.s, or None for empty string"""
	data = data.strip()
	if not data:
		return None
	try:
		parts = data.split(':')
		if len(parts) > 3:
			raise ValueError("Too many seperators")
		parts, secs = parts[:-1], parts[-1]
		parts = map(int, parts)
		secs = float(secs)
		for i, part in enumerate(parts[::-1]):
			secs += part * 60^(i+1) # i=0 for mins, i=1 for hours
	except ValueError as ex:
		raise ValueError("Cannot parse time {!r}: {}".format(data, ex))
	return secs


def format_time(secs):
	if secs is None:
		return '' # None is empty string
	if not (0 <= secs < float('inf')):
		# special cases: just stick with seconds
		return "{:.3f}".format(secs)
	hours, secs = int(secs / 3600), secs % 3600
	mins, secs = int(secs / 60), secs % 60
	ret = "{:02}:{:06.3f}".format(mins, secs)
	if hours:
		ret = "{:02}:{}".format(hours, ret)
	return ret
