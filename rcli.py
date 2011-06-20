#!/usr/bin/env python
import urllib2
import json
import os
import sys

# ------------------------------- TYPER HERE YOUR HASCODE ----------------------------------
HASHCODE = ''
# ------------------------------------------------------------------------------------------
from keys import HASHCODE

if len(sys.argv) < 2:
    print """\
Usage: ./rcli.py Some text
"""
    sys.exit(0)

status = sys.argv[1:]
status = ' '.join(status)

jdata = json.dumps({"hash": HASHCODE, "status": status})

f = urllib2.urlopen("http://ci.local/api/message", jdata)
print f.read()

"""
HOME_DIR = os.getenv("HOME")
path = HOME_DIR + '/.retwis'

if not os.path.exists():
    f = open(path, 'w')
	f.write('')
	f.close()

for line in open(path):
    if line.startswith('login='):
        login = line[6:]
    elif line.startswith('hash='):
        hash = line[5:]

if not login or not hash:
    login = raw_input('Login:')
    password = raw_input('Password:')

# Now go and register


# Whatever structure you need to send goes here:
hash = '57132716327467367173128543205886802271'

jdata = json.dumps({"hash": hash, "status": status})

f = urllib2.urlopen("http://127.0.0.1:80/api/message", jdata)
print f.read()
"""
