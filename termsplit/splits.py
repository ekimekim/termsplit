

from termsplit.timing import parse_time, format_time


class Splits(object):
	r"""Splits are a list of time records. Each split consists of a name, a best time for completing that split,
	and the time that split took in the best overall run.

	The on-disk format is designed to be editable by hand. It consists of lines as follows:
		{name}\t{best time}\t{time of split in best run}\n
	Note that best time is elapsed since start of split,
	whereas time of split in best run is elapsed since the start of the run.

	For example, suppose I was timing a racing game with a 3-lap structure. Suppose my lap times were
	31s, 30s and 32s, and this was my first run (so they are both my best split times and my best overall).
	Then the resulting file would look like:
		First Lap	00:31.00	00:31.00
		Second Lap	00:30.00	01:01.00
		Third Lap	00:32.00	01:33.00

	A note on time formats:
		The following time formats are accepted:
			seconds alone, eg. 3661.05
			M:S, eg. 61:01.05 or 61:1.05
			H:M:S, eg. 1:01:01.05 or 1:1:1.05
		The program will produce time in the format [H:]MM:SS.sss, eg. 1:01:01.050
	"""
	splits = None # list of (name, best time, time in best run)

	def __init__(self, filepath=None):
		"""Optionally load from path"""
		self.splits = []
		if filepath:
			self.loadfile(filepath)

	def __iter__(self):
		"""Iterate over rows (name, best time, time in best run)"""
		return iter(self.splits)

	def __eq__(self, other):
		return isinstance(other, Splits) and other.splits == self.splits

	def copy(self):
		ret = Splits()
		ret.load(self.dump())
		return ret

	def load(self, data):
		for line in data.split('\n'):
			line = line.strip()
			if not line:
				continue
			parts = line.split('\t')
			parts = parts[:3] # ignore columns past the third
			parts += [''] * (3 - len(parts)) # pad with '' to 3 members
			name, best, time = parts
			best = parse_time(best)
			time = parse_time(time)
			self.splits.append((name, best, time))

	def dump(self):
		return '\n'.join("{}\t{}\t{}".format(name, format_time(best), format_time(time))
		                 for name, best, time in self)

	def loadfile(self, filepath):
		with open(filepath) as f:
			data = f.read()
		self.load(data)

	def savefile(self, filepath):
		data = self.dump()
		with open(filepath, 'w') as f:
			f.write(data + '\n')

	def append(self, name, best, time):
		self.splits.append((name, best, time))

	def merge(self, new):
		# TODO merge bests (keep better), merge full time if lengths match
