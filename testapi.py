import urllib2
import json
# Whatever structure you need to send goes here:
hash = '57132716327467367173128543205886802271'
status = """\
This is a new test status
"""

jdata = json.dumps({"hash": hash, "status": status})

f = urllib2.urlopen("http://127.0.0.1:80/api/message", jdata)
print f.read()
