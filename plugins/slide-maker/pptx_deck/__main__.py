import sys

from .cli import entry

sys.exit(entry(sys.argv[1:]))
