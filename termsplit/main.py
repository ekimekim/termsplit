
import json
import os

from argh import EntryPoint, arg, confirm, named

from termsplit.keys import KEYPRESS_EVENTS, KeyPresses
from termsplit.ui import UI
from termsplit.splits import Splits


cli = EntryPoint()


@cli
@arg('--conf', default=None, help='Config file to use, default ~/.termsplit.json')
def configure(conf=None):
	"""Interactive configuration setup. Conf file will be created if it doesn't exist."""
	if not conf:
		conf = os.path.expanduser('~/.termsplit.json')
	if os.path.exists(conf):
		with open(conf) as f:
			config = json.loads(f.read())
	else:
		config = {}

	for event, description in KEYPRESS_EVENTS.items():
		print '{}: {}'.format(event, description)
		if event in config and confirm('Current value: {}. Keep this value'.format(config[event]), True):
			print
			continue
		raw_input("Press Enter when ready.")
		iterator = KeyPresses() # we only capture presses after this line
		print "Now press the button to bind."
		key_name = iterator.next()
		config[event] = key_name
		print "Bound {} to {}".format(event, key_name)
		print

	dump = json.dumps(config, indent=4)
	print "Final config:"
	print dump

	with open(conf, 'w') as f:
		f.write(dump + '\n')


@cli
@arg('--conf', help='Config file to use, default ~/.termsplit.json')
@named('open')
def open_splits(splitfile, conf=None):
	"""Open the given splits file and bring up the main timer interface."""
	if not conf:
		conf = os.path.expanduser('~/.termsplit.json')
	with open(conf) as f:
		config = json.loads(f.read())
	splits = Splits(splitfile)
	UI(config, splits, splitfile).main()
