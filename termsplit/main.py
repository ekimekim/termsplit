
import json

from argh import EntryPoint, arg, confirm


cli = EntryPoint()


@cli
def configure(conf=None):
	"""Interactive configuration setup. Conf file will be created if it doesn't exist.
	Default config is ~/.termsplit.json"""
	if not conf:
		conf = os.path.expanduser('~/.termsplit.json')
	if os.path.exists(conffile):
		with open(conffile) as f:
			config = json.loads(f.read())
	else:
		config = {}

	for event, descrption in KEYPRESS_EVENTS.items():
		print '{}: {}'.format(event, description)
		if event in config and confirm('Current value: {}. Keep this value'.format(config[event]), True):
			print
			continue
		raw_input("Press Enter when ready.")
		iterator = get_key_presses() # we only capture presses after this line
		print "Now press the button to bind."
		key_code = iterator.next()
		key_name = KEYCODES[key_code]
		config[event] = key_name
		print "Bound {} to {}".format(event, key_name)
		print

	dump = json.dumps(config, indent=4)
	print "Final config:"
	print dump

	with open(conf, 'w') as f:
		f.write(dump + '\n')


@cli
@arg('--conf', help='Config file to use')
def open(splitfile, conf=None):
	"""Open the given splits file and bring up the main timer interface."""
	if not conf:
		conf = os.path.expanduser('~/.termsplit.json')
	with open(conffile) as f:
		config = json.loads(f.read())
	# TODO
