
import gevent.queue
import gevent.pool

from inputdev import InputDevice

from termsplit.keycodes import KEYCODES


KEYPRESS_EVENTS = {
	'SPLIT': 'Begin timing, and mark each split',
	'UNSPLIT': 'Undo the most recent split (no effect on first split)',
	'SKIP': 'Skip a split without recording the time - useful if you forgot to split on time',
	'PAUSE': 'Pause the timer, or resume a paused timer',
	'STOP': 'Stop timing, saving any best times acquired in that run',
}


class KeyPresses(object):
	"""Generator that yields key codes for key down events recieved from all input devices.
	Captures all presses starting from when the constructor returns."""

	def __init__(self):
		self.event_queue = gevent.queue.Queue() # contains AsyncResults containing key codes or exceptions
		self.group = gevent.pool.Group()
		for device in InputDevice.find(key=lambda value: value is not None):
			self.group.spawn(self.reader, device)

	def reader(self, device):
		try:
			for event in device.read_iter():
				if event.type != 'key' or event.value != 1 or event.code not in KEYCODES:
					continue
				self.enqueue(KEYCODES[event.code])
		except Exception as ex:
			self.enqueue(ex, exception=True)
			raise
		finally:
			device.close()

	def enqueue(self, value, exception=False):
		result = gevent.event.AsyncResult()
		(result.set_exception if exception else result.set)(value)
		self.event_queue.put(result)

	def close(self):
		self.group.kill(block=True)

	def __iter__(self):
		return self

	def next(self):
		return self.event_queue.get().get() # will error if exception occurred in worker
