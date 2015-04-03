
import sys
from termios import ECHO, ECHONL, ICANON

import gevent.event
import gevent.lock
import gevent.pool
import gevent.queue
from argh import confirm
from gevent.fileobject import FileObject

from termhelpers import TermAttrs

from termsplit.timing import Timer, format_time
from termsplit.splits import Splits
from termsplit.keys import KeyPresses

STDIN_KEYS = {
	'h': 'HELP',
	'q': 'QUIT',
	's': 'SAVE',
}

CLEAR = '\x1b[H\x1b[2J'
CLEAR_LINE = '\x1b[2K'

class Quit(Exception):
	pass


class UI(object):
	INTERVAL = 0.01 # time between updates
	HEADER = ['Name', 'Seg Time', 'Time'] # column names
	MSG_DISPLAY_DELAY = 0.5 # How long to pause output to let a message display before clearing

	def __init__(self, config, splits, filepath=None):
		self.config = config
		self.filepath = filepath

		# splits is up-to-date splits, saved is what was last saved to file,
		# results is this run (instead of best times), original is what to compare against
		# (original updates from splits on run start)
		self.splits = splits
		self.saved = splits.copy()
		self.results = None # is None only before starting
		self.original = None

		self._group = gevent.pool.Group()
		self._input_queue = gevent.queue.Queue()
		self._output_lock = gevent.lock.RLock()
		self.running = gevent.event.Event() # whether time is being counted
		self.timer = None # is None only before starting / after finishing

	def get_input(self):
		"""Wait for an input from either global hotkeys or stdin, and return the associated action"""
		return self._input_queue.get()

	def _read_stdin(self):
		while True:
			c = self.stdin.read(1)
			if not c:
				raise EOFError
			if c in STDIN_KEYS:
				self._input_queue.put(STDIN_KEYS[c])

	def _read_hotkeys(self):
		while True:
			key = self.hotkeys.next()
			reverse_config = {v: k for k, v in self.config}
			if key in reverse_config:
				self._input_queue.put(reverse_config[key])

	def output_wrapper(self):
		"""During timing, the state of the screen is somewhat tricky to manage.
		Most of the time, the output loop will be updating the last line.
		This context manager will (on enter) get the output lock (pausing output loop)
		and go to the next line (so we're not writing on a half-written line),
		and (on successful exit) clear the screen + re-write the previous lines (getting back into the state
		that output loop expects)."""
		class _output_wrapper(object):
			def __enter__(self):
				self._output_lock.acquire()
				print
			def __exit__(self, *exc_info):
				if exc_info == (None, None, None):
					self.clear()
				self._output_lock.release()
		return _output_wrapper()

	def clear(self):
		"""Clear the screen and re-write the preamble"""
		sys.stdout.write(CLEAR) # goto (0,0) and clear screen
		self.preamble()
		sys.stdout.flush()

	def compare(self, original, result):
		"""Takes a best times row, and a results row, and returns a row describing the difference"""
		compared = []
		for o_time, r_time in zip(original, result):
			if r_time is None:
				# r_time is None, no comparison
				output = '-'
			elif o_time is None:
				# if original is None, return (result)
				output = '({})'.format(format_time(r_time))
			else:
				output = r_time - o_time
			compared.append(output)
		return compared

	def get_compare_rows(self, results):
		return map(self.compare, zip(self.original, results))

	def main(self):
		"""Run the main UI for the given splits.
		The UI makes heavy use of terminal escape sequences, and has two methods of input:
		The configured global hotkeys, and characters read from stdin. In general, hotkeys are used for
		"live" operations like splitting and pausing, whereas stdin is used for administrative operations like
		saving the splitfile or reconfiguring."""
		with TermAttrs.modify(exclude=(0,0,0,ECHO|ECHONL|ICANON)): # don't echo input, one-char-at-a-time
			self.hotkeys = KeyPresses()
			self.stdin = FileObject(sys.stdin)

			self.preamble()
			sys.stdout.flush()

			self._group.spawn(self._read_stdin)
			self._group.spawn(self._read_hotkeys)
			self._group.spawn(self.input_loop)
			self._group.spawn(self.output_loop)

			# raise if any greenlet fails
			try:
				gevent.pool.Group().map(lambda g: g.get(), self._group.greenlets)
			except Quit:
				with self._output_lock:
					print
					if self.saved != self.splits and confirm("Your splits have changed. Save them", default=True):
						self.save()
			finally:
				self._group.kill()
				print

	def preamble(self):
		print "Current times:"
		self.print_splits(self.splits)
		print
		print
		self.print_splits(self.get_compare_rows(self.results))
		self.print_current()

	def get_widths(self, rows):
		"""Given a list of rows, returns the max width for the first two columns."""
		name_lens = []
		best_lens = []
		for name, best, time in rows:
			if not isinstance(best, basestring):
				best = format_time(best)
			name_lens.append(len(name))
			best_lens.append(len(best))
		return max(name_lens), max(best_lens)

	def print_splits(self, rows):
		widths = self.get_widths(rows)
		self.print_header(widths)
		for row in rows:
			self.print_row(widths, *row)

	def print_header(self, widths):
		"""Print header but with padding to fit columns"""
		self.print_row(widths, *self.HEADER)

	def get_current_row(self, split=False):
		"""Return the times for the current row. If split=True, begin the next split.
		(if splitting were a seperate operation, a small delay would be introduced between get() and mark())
		"""
		name, _, _ = self.splits[len(self.results)] # next split after the ones in results
		return name, self.timer.mark(peek=not split), self.timer.get()

	def print_current(self, current=None):
		"""Print times for the current split based on self.timer.
		Does NOT end with a newline."""
		split = self.original[len(self.results)] # next split after the ones in results
		if not current:
			current = self.get_current_row()
		widths = self.get_widths(self.get_compare_rows(self.results + [current]))
		self.print_row(widths, self.compare(split, current), newline=False)

	def print_row(self, widths, name, best, time, newline=True):
		"""Print the given row with padding to fit columns"""
		if not isinstance(best, basestring):
			best = format_time(best)
		if not isinstance(time, basestring):
			time = format_time(time)
		sys.stdout.write("{:<{widths[0]}}  {:<{widths[1]}}  {}".format(name, best, time, widths=widths))
		if newline:
			sys.stdout.write('\n')

	def save(self):
		with self.output_wrapper():
			self._save()
			gevent.sleep(self.MSG_DISPLAY_DELAY)

	def _save(self):
		filepath = self.filepath
		# we keep asking for a filepath until they cancel - this is safer than only giving them one try
		with self._output_lock:
			while True:
				if not filepath:
					try:
						filepath = raw_input("Please enter file path to save to, or nothing to cancel: ")
					except EOFError:
						filepath = ''
				if not filepath:
					return # return without saving
				try:
					self.splits.savefile(self.filepath)
				except EnvironmentError as ex:
					print ex
					filepath = None # try entering different path
				else:
					break
		# remember the new save details
		self.saved = self.splits.copy()
		self.filepath = filepath
		print 'Saved to {}'.format(filepath)

	def help(self):
		pass # TODO

	def split(self):
		if not self.timer:
			if self.results:
				return # post-finish, do nothing (must hit reset to begin a new run)
			self.start() # start the clock!
			return
		# record the time for this split
		with self._output_lock:
			current = self.get_current_row(split=True)
			# refresh current line to make sure it's up to date
			sys.stdout.write(CLEAR_LINE)
			self.print_current(current)
			print # add a newline to begin next split's line
			self.results.append(current)
			if len(self.results) == len(self.splits):
				# run over
				self.finish()
			else:
				self.print_current() # now print the new split

	def start(self):
		self.results = Splits()
		self.original = self.splits.copy()
		self.timer = Timer()
		self.running.set()

	def finish(self):
		self.timer = None
		self.running.clear()

	def reset(self):
		self.finish()
		self.splits.merge(self.results)
		self.results = None

	def pause(self):
		if not self.timer:
			return # not started - do nothing
		self.timer.pause() # toggle pause
		if self.timer.paused:
			self.running.clear()
		else:
			self.running.set()

	def quit(self):
		raise Quit

	def _output_loop(self):
		while True:
			self.running.wait()
			with self._output_lock:
				if not self.running.is_set():
					# race cdn: we stopped running between running.wait() and now - do nothing
					continue
				# at this time we assume the cursor is at the end of print_current()/preamble()
				# we clear the current line, and re-print it
				sys.stdout.write(CLEAR_LINE)
				self.print_current()
				sys.stdout.flush()

	def _input_loop(self):
		ACTION_MAP = {
			'HELP': self.help,
			'SAVE': self.save,
			'QUIT':	self.quit,
			'SPLIT': self.split,
#			'UNSPLIT': self.unsplit, # TODO
#			'SKIP': self.skip, # TODO
			'PAUSE': self.pause,
			'STOP': self.reset,
		}
		while True:
			action = self.get_input()
			ACTION_MAP[action]()
