
import sys
import errno
from termios import ECHO, ECHONL, ICANON

import gevent.event
import gevent.socket
import gevent.lock
import gevent.pool
import gevent.queue

import gtools
from termhelpers import TermAttrs

from termsplit.timing import Timer, format_time
from termsplit.splits import Splits
from termsplit.keys import KeyPresses

STDIN_KEYS = {
	'h': 'HELP',
	'q': 'QUIT',
	's': 'SAVE',
	'r': 'REDRAW',
}

CLEAR = '\x1b[H\x1b[2J'
CLEAR_LINE = '\x1b[2K\x1b[G'

class Quit(gevent.GreenletExit):
	pass


class UI(object):
	INTERVAL = 0.01 # time between updates
	HEADER = ['Name', 'Seg Time', 'Best Seg', 'PB Seg', 'Time', 'PB Time'] # column names
	SPLITS_HEADER = ['Name', 'Best Seg', 'PB Time']
	MSG_DISPLAY_DELAY = 0.5 # How long to pause output to let a message display before clearing

	def __init__(self, config, splits, filepath=None):
		self.config = config
		self.filepath = filepath

		# splits is up-to-date splits, saved is what was last saved to file,
		# results is this run (instead of best times)
		self.splits = splits
		self.saved = splits.copy()
		self.results = None

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
			try:
				r, w, x = gevent.select.select([sys.stdin], [], [])
			except EnvironmentError as ex:
				if ex.errno != errno.EINTR:
					raise
				continue
			if r:
				c = sys.stdin.read(1)
				if not c:
					raise EOFError
				if c in STDIN_KEYS:
					self._input_queue.put(STDIN_KEYS[c])

	def _read_hotkeys(self):
		while True:
			key = self.hotkeys.next()
			reverse_config = {v: k for k, v in self.config.items()}
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
			def __enter__(wrapper):
				self._output_lock.acquire()
				print
			def __exit__(wrapper, *exc_info):
				if exc_info == (None, None, None):
					self.clear()
				self._output_lock.release()
		return _output_wrapper()

	def clear(self):
		"""Clear the screen and re-write the preamble"""
		sys.stdout.write(CLEAR) # goto (0,0) and clear screen
		self.preamble()
		sys.stdout.flush()

	def compare(self, split_index, result):
		"""Takes a splits row, and a results row, and returns a row describing the difference"""
		name, best_seg, pb_time = self.splits[split_index]
		pb_seg = self.splits.best_run_segment_time(split_index)
		_, result_seg, result_time = result

		def diff(o_time, r_time):
			if r_time is None:
				# r_time is None, no comparison
				return '-'
			elif o_time is None:
				# if original is None, return (result)
				return '({})'.format(format_time(r_time))
			else:
				return r_time - o_time

		return [
			name,
			result_seg,
			diff(best_seg, result_seg),
			diff(pb_seg, result_seg),
			result_time,
			diff(pb_time, result_time),
		]

	def get_compare_rows(self, results):
		return [self.compare(idx, result) for idx, result in enumerate(results)]

	def main(self):
		"""Run the main UI for the given splits.
		The UI makes heavy use of terminal escape sequences, and has two methods of input:
		The configured global hotkeys, and characters read from stdin. In general, hotkeys are used for
		"live" operations like splitting and pausing, whereas stdin is used for administrative operations like
		saving the splitfile or reconfiguring."""
		with TermAttrs.modify(exclude=(0,0,0,ECHO|ECHONL|ICANON)): # don't echo input, one-char-at-a-time
			self.hotkeys = KeyPresses()

			self.clear()
			sys.stdout.flush()

			self._group.spawn(self._read_stdin)
			self._group.spawn(self._read_hotkeys)
			self._group.spawn(self.input_loop)
			self._group.spawn(self.output_loop)

			# raise if any greenlet fails, continue if Quit raised
			try:
				gtools.get_first([g.get for g in self._group.greenlets])
			finally:
				if self.saved != self.splits:
					print
					print 'Exiting with unsaved changes! Dumping splitfile:'
					print self.splits.dump()
				self._group.kill()
				print

	def preamble(self):
		print "Current times:"
		self.print_splits()
		print
		print
		if self.timer: # if started
			self.print_results(self.get_compare_rows(self.results))
			self.print_current()

	def get_widths(self, header, rows, min_widths=None):
		"""Given a list of rows, returns the max width for the first two columns."""
		rows = [self.convert_row(row) for row in rows]
		longest = list(min_widths) if min_widths is not None else [0 for _ in header]
		for row in [header] + list(rows):
			longest = [max(a, len(b)) for a, b in zip(longest, row)]
		return longest

	def get_result_widths(self, rows):
		all_equal = [self.compare(idx, split) for idx, split in enumerate(self.splits)]
		min_widths = self.get_widths(self.HEADER, all_equal)
		return self.get_widths(self.HEADER, rows, min_widths)

	def convert_row(self, row):
		return [v if isinstance(v, str) else format_time(v) for v in row]

	def print_splits(self):
		widths = self.get_widths(self.SPLITS_HEADER, self.splits)
		self.print_row(widths, self.SPLITS_HEADER)
		for row in self.splits:
			self.print_row(widths, row)

	def print_results(self, rows):
		widths = self.get_result_widths(rows)
		self.print_row(widths, self.HEADER)
		for row in rows:
			self.print_row(widths, row)

	def get_current_row(self, split=False):
		"""Return the times for the current row. If split=True, begin the next split.
		(if splitting were a seperate operation, a small delay would be introduced between get() and mark())
		"""
		name, _, _ = self.splits[len(self.results)] # next split after the ones in results
		return name, self.timer.mark(peek=not split), self.timer.get()

	def print_current(self, current=None):
		"""Print times for the current split based on self.timer.
		Does NOT end with a newline."""
		split_index = len(self.results) # next split after the ones in results
		if not current:
			current = self.get_current_row()
		widths = self.get_result_widths(self.get_compare_rows(list(self.results) + [current]))
		self.print_row(widths, self.compare(split_index, current), newline=False)

	def print_row(self, widths, row, newline=True):
		"""Print the given row with padding to fit columns"""
		row = self.convert_row(row)
		row = "  ".join(
			"{value:<{width}}".format(width=width, value=value)
			for width, value in zip(widths, row)
		)
		if newline:
			row += "\n"
		sys.stdout.write(row)

	def save(self):
		with self.output_wrapper():
			self._save()
			gevent.sleep(self.MSG_DISPLAY_DELAY)

	def _save(self):
		self.splits.savefile(self.filepath)
		# remember the new save details
		self.saved = self.splits.copy()
		print 'Saved to {}'.format(self.filepath)

	def help(self):
		with self.output_wrapper():
			print "Help:"
			for key, action in STDIN_KEYS.items():
				print "\t{}: {}".format(key, action)
			for action, key in self.config.items():
				print "\t{}: [global] {}".format(key, action)
			(help_key,) = [key for key, action in STDIN_KEYS.items() if action == "HELP"]
			print "Press {} again to dismiss".format(help_key)
			# Block until any input.
			# If it's another HELP, consume it. Otherwise leave it for the main input loop.
			if self._input_queue.peek() == "HELP":
				self.get_input()

	def split(self):
		if not self.timer:
			if self.results is not None:
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
			self.results.append(*current)
			if len(self.results) == len(self.splits):
				# run over
				self.finish()
			else:
				self.print_current() # now print the new split

	def unsplit(self):
		if not self.timer:
			return # not running, do nothing
		if len(self.results) == 0:
			return # can't unsplit the first split
		self.timer.unmark()
		self.results.pop()
		self.clear()

	def skip(self):
		if not self.timer:
			return # not running, do nothing
		if len(self.results) == len(self.splits) - 1:
			return # can't skip final split
		with self._output_lock:
			# replace current line with empty
			name, _, _ = self.get_current_row()
			current = (name, None, None)
			sys.stdout.write(CLEAR_LINE)
			self.print_current(current)
			self.results.append(*current)
			print # next line for next split
			self.print_current()

	def start(self):
		self.results = Splits()
		self.timer = Timer()
		self.running.set()
		self.clear()

	def finish(self):
		self.timer = None
		self.running.clear()

	def reset(self):
		if self.results is None:
			return # already reset
		self.finish()
		self.splits.merge(self.results)
		self.results = None
		self.clear()

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

	def output_loop(self):
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
			gevent.sleep(self.INTERVAL)

	def input_loop(self):
		ACTION_MAP = {
			'HELP': self.help,
			'SAVE': self.save,
			'QUIT':	self.quit,
			'REDRAW': self.clear,
			'SPLIT': self.split,
			'UNSPLIT': self.unsplit,
			'SKIP': self.skip,
			'PAUSE': self.pause,
			'STOP': self.reset,
		}
		while True:
			action = self.get_input()
			if action not in ACTION_MAP:
				continue # unimplemented
			ACTION_MAP[action]()
