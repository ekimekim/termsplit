from setuptools import setup

setup(
	name = "termsplit",
	version = "0.1",
	description = "Terminal-based splits timer with global hotkey support",
	author = "Mike Lang",
	author_email = "mikelang3000@gmail.com",
	packages = ['termsplit'],
	install_requires = [
		'gevent',
		'inputdev',
		'argh',
		'monotonic',
		'gtools',
		'termhelpers',
	],
	entry_points = {'console_scripts':['termsplit = termsplit.main:cli']},
)
