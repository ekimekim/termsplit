
from monotonic import monotonic


class Timer(object):
	"""A stateful timer object that can be started, paused, and marked (see mark()).
	Cannot be stopped or reset - just make a new one.
	Uses monotonic time.
	"""
	extra_time = 0 # extra_time is a base value to add to elapsed time, used to implement pause
	paused = False

	def __init__(self):
		self.start_time = monotonic()
		self.marks = [] # list of elapsed times that marks are made at - last entry is current mark

	def get(self):
		"""Return the time elapsed since start"""
		elapsed, now = self._get()
		return elapsed

	def _get(self):
		"""Retuns (elapsed since start, timestamp of when this elapsed time was retrieved)"""
		now = monotonic()
		elapsed = self.extra_time
		if not self.paused:
			elapsed += now - self.start_time
		return elapsed, now

	def pause(self):
		"""Toggle between paused and unpaused"""
		if self.paused:
			self.start_time = monotonic()
			self.paused = False
		else:
			self.extra_time = self.get()
			self.paused = True

	def mark(self, peek=False):
		"""Marks the current time, and returns the elapsed time since the last mark.
		If peek=True, return elapsed time without changing the mark."""
		elapsed = self.get()
		old_mark = self.marks[-1] if self.marks else 0
		since_mark = elapsed - old_mark
		if not peek:
			self.marks.append(elapsed)
		return since_mark

	def unmark(self):
		"""Undo the latest mark (if any), so the next mark will return the time since the previous mark.
		Example:
			t=1: start
			t=2: mark (returns 1)
			t=3: unmark
			t=4: mark (returns 3)
		"""
		if self.marks:
			self.marks.pop()


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
