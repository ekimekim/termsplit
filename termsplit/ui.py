

STDIN_KEYS = {
	'h': 'help',
	'q': 'quit',
	's': 'save',
}


class UI(object):
	self.INTERVAL = 0.01 # time between updates

	def __init__(self, config, splits):
		self.config = config
		self.splits = splits
		self._group = gevent.pool.Group()
		self._input_queue = gevent.queue.Queue()

	def get_input(self):
		"""Wait for an input from either global hotkeys or stdin, and return the associated action"""
		return self._input_queue.get().get()

	def _push_input(self, func):
		def wrap(value):
			wrapper = AsyncResult()
			if isinstance(value, Exception):
				wrapper.set_exception(value)
			else:
				wrapper.set(value)
			return wrapper
		try:
			while True:
				self._input_queue.put(wrap(func()))
		except Exception as ex:
			# push the error so get_input recieves it
			self._input_queue.put(wrap(ex))

	def _read_stdin(self):
		while True:
			c = self.stdin.read(1)
			if not c:
				raise EOFError
			if c in STDIN_KEYS:
				return STDIN_KEYS[c]

	def _read_hotkeys(self):
		while True:
			key = self.hotkeys.next()
			reverse_config = {v: k for k, v in self.config}
			if key in reverse_config:
				return reverse_config[key]

	def main(self):
		"""Run the main UI for the given splits.
		The UI makes heavy use of terminal escape sequences, and has two methods of input:
		The configured global hotkeys, and characters read from stdin. In general, hotkeys are used for
		"live" operations like splitting and pausing, whereas stdin is used for administrative operations like
		saving the splitfile or reconfiguring."""
		with TermAttrs.modify(exclude=(0,0,0,ECHO|ECHONL|ICANON)): # don't echo input, one-char-at-a-time
			self.hotkeys = KeyPresses()
			self.stdin = FileObject(sys.stdin)
			self.timer = None
			self._group.spawn(self._push_input, self._read_stdin)
			self._group.spawn(self._push_input, self._read_hotkeys)

			self.preamble()

			self._group.spawn(self.input_loop)
			self._group.spawn(self.output_loop)

	def preamble(self):
		print "Current times:"
		self.print_splits()
		print

	def print_splits(self):
		widths = self.get_widths()
		self.print_header(widths)
		for row in self.splits:
			self.print_row(widths, *row)

	def print_header(self, widths):
		"""Print header "Name   Seg Time   Time" but with padding to fit columns"""
		print "{:<{widths[0]}}  {:<{widths[1]}}  {}".format("Name", "Seg Time", "Time", widths=widths)

	def print_row(self, widths, name, best, time, colors=(None, None)):
		"""Print the given row with padding to fit columns.
		Optional arg colors can assign terminal foreground colors (eg. '1' for red)
		to best and time args respectively.
		"""
		colors = ['\x1b[3{}m'.format(color) if color is not None else '' for color in colors]
		print "{:<{widths[0]}}  {colors[0]}{:<{widths[1]}}{reset}  {colors[1]}{}{reset}".format(
			name, best, time, widths=widths, colors=colors, reset='\x1b[m',
		)
