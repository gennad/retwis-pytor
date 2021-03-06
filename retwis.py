#!/usr/bin/env python
#
# Copyright (c) 2011 Andrew Zeneski
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

""" Retwis-PyTor Tornado Web Application.

Based on the retwis (0.3) PHP [example] application provided by Redis at redis.io
This is complete re-write in Python using the Tornado framework

Dependencies:
Tornado: https://github.com/alexdong/tornado
Redis-Py: https://github.com/andymccurdy/redis-py
Redis: http://redis.io

Usage:
python ./retwis.py
"""

import json
import random
import re

import tornado.httpserver
import tornado.ioloop
import tornado.options
import tornado.web
import os.path
import logging
import string
import redis
import time
import uuid

from tornado.options import define, options

define("port", default=80, help="run on the given port", type=int)
define("redis_host", default="localhost", help="redis server")
define("redis_port", default=6379, help="redis port", type=int)

class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            (r"/", MainHandler),
            (r"/home/", MainHandler),
            (r"/post", PostHandler),
            (r"/logout/", LogoutHandler),
            (r"/login/", LoginHandler),
            (r"/profile", ProfileHandler),
            (r"/follow", FollowHandler),
            (r"/register/(\w*)", RegisterHandler),
            #(r"/timeline/", TimelineHandler),
            #("/api/(\d+)?/?", APIHandler),
            ("/api/register/", APIRegister),
            ("/api/(\w*)/*", APIHandler),
        ]
        settings = dict(
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            ui_modules={"Post": PostModule},
            cookie_secret="11oETzKXQAGaYdkL5gEmGeJJFuYh7EQnp2XdTP1o/Vo=",
            xsrf_cookies=False,
        )
        tornado.web.Application.__init__(self, handlers, **settings)
        tornado.options.parse_command_line()
        self.redis_cli = redis.Redis(host=options.redis_host,
                                     port=options.redis_port, db=0)


class BaseHandler(tornado.web.RequestHandler):
    def get_client(self):
            return redis.Redis(host=options.redis_host,
                port=options.redis_port, db=0)

    def get_current_user(self):
        auth_cookie = self.get_secure_cookie("auth")
        if not auth_cookie:
            logging.info("No auth cookie; user not logged in")
            return None

        user_id = self.get_client().get("auth:" + auth_cookie);
        if not user_id:
            logging.info("No user_id for cookie found in redis ")
            return None

        username = self.get_client().get("uid:" + user_id + ":username")
        return dict(user_id=user_id, username=username)


    def get_api_user(self, user_id):
        username = self.get_client().get("uid:" + user_id + ":username")
        return dict(user_id=user_id, username=username)

    def save_auth_token(self, user_id):
        auth_uid = str(uuid.uuid4())
        self.get_client().set("uid:" + user_id + ":auth", auth_uid)
        self.get_client().set("auth:" + auth_uid, user_id)
        self.set_secure_cookie('auth', auth_uid, 365)

    def do_error(self, message):
        self.render("error.html", message=message)

class MainHandler(BaseHandler):
    def get(self):
        user = self.get_current_user()
        if not user:
            self.render("welcome.html")
        else:
            # range
            start = self.get_argument("start", 0)
            count = self.get_argument("count", 10)

            # followers/following
            followers = self.get_client().scard("uid:" + user['user_id'] + ":followers")
            following = self.get_client().scard("uid:" + user['user_id'] + ":following")

            # posts
            """
            Only user's posts:
            posts = self.get_client().lrange("uid:" + user['user_id'] + ":posts", start, (start + count))
            if posts is None:
                posts = []
            """
            # All posts
            posts = self.get_client().lrange("global:timeline", 0, 50)

            # render page
            self.render("home.html", posts=posts, client=self.get_client(), followers=followers, following=following)            

class TimelineHandler(BaseHandler):
    def get(self):
        last_users = self.get_client().sort("global:users", 0, 10, None,
                "uid:*:username", True)
        last_posts = self.get_client().lrange("global:timeline", 0, 50)
        self.render("timeline.html", posts=last_posts, users=last_users,
                client=self.get_client())


class PostHandler(BaseHandler):
    def post(self):
        # current user
        user = self.get_current_user()

        # create the post
        status = string.replace(self.get_argument("status"), "\n", "")
        status = Validator.validate(status)

        splitted = status.split()
        splitted = map(lambda x: x[0:100] if len(x) > 100 else x, splitted)
        status = ' '.join(splitted)

        post_id = self.get_client().incr("global:nextPostId")
        post = user['user_id'] + "|" + str(time.time()) + "|" + status
        self.get_client().set("post:" + str(post_id), post)

        # get all followers
        followers = self.get_client().smembers("uid:" + user['user_id'] + ":followers")
        if not followers: followers = set()
        followers.add(user['user_id'])

        # push the post to all followers
        for fid in followers:
            self.get_client().lpush('uid:' + fid + ":posts", post_id)

        # push the post to the timeline and trim the timeline to 1000 elements
        self.get_client().lpush('global:timeline', post_id);
        self.get_client().ltrim('global:timeline', 0, 1000);

        # refresh the page
        self.redirect("/home/")


class ProfileHandler(BaseHandler):
    def get(self):
        user = self.get_current_user()

        member_name = self.get_argument("u", None)
        if not member_name:
            logging.info("no member name passed")
            self.do_error("User not found.")
            return

        # check for the user
        member_id = self.get_client().get("username:" + member_name + ":id")
        if not member_id:
            logging.info("member not found in datastore")
            self.do_error("User not found.")
            return

        is_following = self.get_client().sismember("uid:" + user['user_id'] +
                ":following", member_id)
        logging.info(user['username'] + " following " + member_name + " ? " + str(is_following))

        posts = self.get_client().lrange("uid:" + member_id + ":posts", 0, 10)
        self.render("profile.html", posts=posts, client=self.get_client(),
                    is_following=is_following, member_name=member_name,
                    member_id=member_id)


class FollowHandler(BaseHandler):
    def get(self):
        user = self.get_current_user()

        uid = self.get_argument("uid", None)
        fol = self.get_argument("f", None)
        if not uid or not fol:
            self.do_error("Sorry, your request could not be processed; please try again.")
            return
        else:
            member_name = self.get_client().get("uid:" + uid + ":username")
            if int(fol):
                # follow
                self.get_client().sadd("uid:" + uid + ":followers", user['user_id'])
                self.get_client().sadd("uid:" + user['user_id'] + ":following", uid)
            else:
                # stop
                self.get_client().srem("uid:" + uid + ":followers", user['user_id'])
                self.get_client().srem("uid:" + user['user_id'] + ":following", uid)

            self.redirect("/profile?u=" + member_name)


class RegisterHandler(BaseHandler):
    def post(self, param):
        user = self.get_current_user();
        if user:
            self.redirect("/home/")
        else:
            username = self.get_argument("username", None)
            password = self.get_argument("password", None)
            passconf = self.get_argument("passconf", None)
            if not username or not password:
                self.do_error("You must enter a username and password to register.")
                return
            if password != passconf:
                self.do_error("Your password does not match.")
                return
            pattern = '^[a-zA-Z0-9_-]+$'
            prog = re.compile(pattern)
            result = prog.match(username)
            if not result:
                self.do_error("Your username is not valid.")
                return

            if len(username) > 30:
                self.do_error("The length of username can not be more than 30 letters.")
                return

            # check if username is available
            if (self.get_client().get("username:" + username + ":id")):
                self.do_error("Sorry, the selected username is already taken.")
                return

            # register the user
            user_id = str(self.get_client().incr("global:nextUserId"))
            self.get_client().set("uid:" + user_id + ":username", username)
            self.get_client().set("uid:" + user_id + ":password", password)
            self.get_client().set("username:" + username + ":id", user_id)
            self.get_client().sadd("global:users", user_id) # add to global users
            self.save_auth_token(user_id)

            self.render("registered.html", username=username)



class LoginHandler(BaseHandler):
    def post(self):
        if not self.current_user:
            username = self.get_argument("username", None)
            password = self.get_argument("password", None)
            if not username or not password:
                self.do_error("You need to enter both username and password to login.");
                return

            user_id = self.get_client().get("username:" + username + ":id")
            if not user_id:
                self.do_error("Username not found.");
                return

            redis_pass = self.get_client().get("uid:" + user_id + ":password")
            if not password == redis_pass:
                self.do_error("Wrong useranme or password.");
                return

            self.save_auth_token(user_id)
            self.redirect("/home/")
        else:
            self.redirect("/home/")


class LogoutHandler(BaseHandler):
    def get(self):
        self.clear_cookie("auth")
        self.redirect("/home/")


class PostModule(tornado.web.UIModule):
    def get_elapsed(self, t):
        logging.info("Time : " + str(time.time()) + " -- Post: " + t)
        diff = time.time() - float(t)
        logging.info("Time diff : " + str(diff))
        if (diff < 60): return str(int(diff)) + (" seconds" if diff > 1 else " second")
        if (diff < 3600): return str(int(diff/60)) + (" minutes" if (diff/60) > 1 else " minute")
        if (diff < 3600*24): return str(int(diff/3600)) + (" hours" if (diff/3600) > 1 else " hour") 
        return str(int(diff/(3600*24))) + " " + ("days" if (diff/(3600*24)) > 1 else "day")

    def render(self, post, client):
        post_data = client.get("post:" + post)
        logging.info("Rendering post : " + post_data)
        post_list = post_data.split("|", 3)
        elapsed = self.get_elapsed(post_list[1])
        data = post_list[2]
        data = Validator.validate(data)

        splitted = data.split()
        splitted = map(lambda x: x[0:100] if len(x) > 100 else x, splitted)
        data = ' '.join(splitted)

        username = client.get("uid:" + post_list[0] + ":username")
        if len(username) > 30:
            username = username[0:30]
        username = Validator.validate(username)
        return self.render_string("modules/post.html", post=data, elapsed=elapsed, username=username)

class APIRegister(BaseHandler):
    def get(self):
        return self.render("api_register.html")
    def post(self):
        username = self.get_argument("username", None)
        password = self.get_argument("password", None)
        passconf = self.get_argument("passconf", None)
        if not username or not password:
            self.do_error("You must enter a username and password to register.")
            return
        if password != passconf:
            self.do_error("Your password does not match.")
            return

        hash = self.generate_hash()

        # check if username is available
        if (self.get_client().get("username:" + username + ":id")):
            self.do_error("Sorry, the selected username is already taken.")
            return

        # register the user
        user_id = str(self.get_client().incr("global:nextUserId"))
        self.get_client().set("uid:" + user_id + ":username", username)
        self.get_client().set("uid:" + user_id + ":password", password)
        self.get_client().set("hash:" + str(hash) + ":id", user_id)
        self.get_client().set("username:" + username + ":id", user_id)
        self.get_client().sadd("global:users", user_id) # add to global users
        self.save_auth_token(user_id)

        self.render("api_registered.html", username=username, hash=hash)

    def generate_hash(self):
        random.seed()
        hash = random.getrandbits(128)
        return hash

    def get_md5_digest(self, st):
        import md5
        m = md5.new()
        m.update(st)
        return m.digest()


class APIHandler(BaseHandler):
    """Handler for API requests."""
    def get(self, action):
        if not action:
            # Render documentation
            return self.render("api.html")
        if action == 'doc':
            # Register app
            return self.render("api_doc.html")

            # return the requested post
        # return all of the posts

    def put(self, post_id):
        if post_id:
            # update the requested post
            return
        # use your imagination

    def post(self, action):
        if action:
            dic = json.loads(self.request.body)
            user_id = self.check_hash(dic['hash'])
            if not user_id:
                pass

            # create the post
            user = self.get_api_user(user_id)
            status = string.replace(dic['status'], "\n", "")
            post_id = self.get_client().incr("global:nextPostId")
            post = user['user_id'] + "|" + str(time.time()) + "|" + status
            self.get_client().set("post:" + str(post_id), post)

            # get all followers
            followers = self.get_client().smembers("uid:" + user['user_id'] + ":followers")
            if not followers: followers = set()
            followers.add(user['user_id'])

            # push the post to all followers
            for fid in followers:
                self.get_client().lpush('uid:' + fid + ":posts", post_id)

            # push the post to the timeline and trim the timeline to 1000 elements
            self.get_client().lpush('global:timeline', post_id);
            self.get_client().ltrim('global:timeline', 0, 1000);

            self.write("OK")
        # use your imagination
        # create a new post

    def delete(self, post_id):
        if post_id:
            # delete the requested post
            return
        # delete all of the posts 

    def check_hash(self, hash):
        user_id = self.get_client().get("hash:" + hash + ":id")
        if not user_id:
            return None

        return user_id

class Auth:
    def check_hash(self):
        pass


class Validator:
    html_escape_table = {
        ">": "&gt;",
        "<": "&lt;",
    }

    @staticmethod
    def validate(text):
        """Produce entities within text."""
        return "".join(Validator.html_escape_table.get(c,c) for c in text)


class MessageMixin(object):
    waiters = []
    cache = []
    cache_size = 200

    def wait_for_messages(self, callback, cursor=None):
        cls = MessageMixin
        if cursor:
            index = 0
            for i in xrange(len(cls.cache)):
                index = len(cls.cache) - i - 1
                if cls.cache[index]["id"] == cursor:
                    break

            recent = cls.cache[index + 1:]
            if recent:
                callback(recent)
                return
        cls.waiters.append(callback)

    def new_messages(self, messages):
        cls = MessageMixin
        logging.info("Sending new message to %r listeners", len(cls.waiters))
        for callback in cls.waiters:
            try:
                callback(messages)
            except:
                logging.error("Error in waiter callback", exc_info=True)
        cls.waiters = []
        cls.cache.extend(messages)
        if len(cls.cache) > self.cache_size:
            cls.cache = cls.cache[-self.cache_size:]


class MessageUpdatesHandler(BaseHandler, MessageMixin):
    @tornado.web.asynchronous
    def post(self):
        cursor = self.get_argument("cursor", None)
        self.wait_for_messages(self.async_callback(self.on_new_messages),
                               cursor=cursor)

    def on_new_messages(self, messages):
        # Closed client connection
        if self.request.connection.stream.closed():
            return
        self.finish(dict(messages=messages))


class BaseHandler(tornado.web.RequestHandler):
    def get_current_user(self):
        user_json = self.get_secure_cookie("user")
        if not user_json: return None
        return tornado.escape.json_decode(user_json)


def main():
    tornado.options.parse_command_line()
    http_server = tornado.httpserver.HTTPServer(Application())
    http_server.listen(options.port)
    tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
    main()
