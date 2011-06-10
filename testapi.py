import urllib2
import json
# Whatever structure you need to send goes here:
jdata = json.dumps({"username":"testusername", "password":"testpassword"})
f = urllib2.urlopen("http://127.0.0.1:80/api/message", jdata)
print f.read()
