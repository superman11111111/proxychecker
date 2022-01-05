import argparse
from json.decoder import JSONDecodeError
import re
import sys
import urllib.request
import socket
from threading import Thread, Event, Lock
from queue import Queue
import time
import json
import os

# Settings
CHECK_PIP = ":4000"  # Public IP of the machine serving /api/headers, I am not automating this for security reasons
PROXY_CHECK_URL = "https://www.myip.com/"
TIMEOUT = 30

# Global variables
ANON_CHECK_URL = ""
NOT_ANON_FLAG = "not_anon"
ANON_FLAG = "anon"
CHECKING_STARTED = False
CHECKING_THREAD = None
ANONCHECKING_THREAD = None
PORT = 0
WORKING_JSON_FH = None
HTTP_ERRORS = ""
# HTTP_ERRORS = "error.log" # Uncomment to log HTTP errors
if HTTP_ERRORS:
    if not os.path.isfile(HTTP_ERRORS):
        open(HTTP_ERRORS, "w").write("")
socket.setdefaulttimeout(TIMEOUT)


class FileHandler:
    __FILEHANDLERS = []

    def __init__(self, path) -> None:
        self.path = path
        self.lock = Lock()
        self.__class__.__FILEHANDLERS.append(self)

    @classmethod
    def create(cls, path):
        if not os.path.isfile(path):
            with open(path, "w"):
                pass
            # print(f"[{cls.__name__}] Not a file: {path}")
        for fh in cls.__FILEHANDLERS:
            if fh.path == path:
                return fh
        return FileHandler(path)

    def open(self, mode, block=True):
        if self.lock.acquire(blocking=block):
            return open(self.path, mode)

    def read(self, block=True) -> str:
        with self.open("r", block=block) as f:
            _read = f.read()
        self.lock.release()
        return _read

    def write(self, text: str, block=True) -> None:
        with self.open("w", block=block) as f:
            f.write(text)
        self.lock.release()


def get(url, proxy_data=dict()):
    try:
        proxy_handler = urllib.request.ProxyHandler(proxy_data)
        opener = urllib.request.build_opener(proxy_handler)
        opener.addheaders = [("User-agent", "Mozilla/5.0")]
        return opener.open(url)
    except Exception as e:
        if HTTP_ERRORS:
            open(HTTP_ERRORS, "a").write(str(e))
    return None


def start_checking(proxy_file="proxies.txt"):
    time.sleep(2)
    if not os.path.isfile(proxy_file):
        print(f"[Error] Proxy file missing: {proxy_file}")
        time.sleep(1)
        global CHECKING_STARTED
        CHECKING_STARTED = False
        return
    print()
    qu = Queue()
    stop_event = Event()
    n_proxies = 0

    def check_proxy(pip):
        global PROXY_CHECK_URL
        start = time.time()
        if get(PROXY_CHECK_URL, {"https": pip}):
            qu.put((time.time() - start, pip))

    def consume_queue():
        old_working = []
        _read = WORKING_JSON_FH.read()
        try:
            old_working = json.loads(_read)
        except JSONDecodeError:
            pass
        working = []
        i = 0
        while True:
            if stop_event.is_set():
                break
            if not qu.empty():
                t, pip = qu.get(block=False)
                _print = f"{i}/{n_proxies} {round(t, 4)} {pip}  "
                print(f"\r{_print}{(50 - len(_print))*' '}", end="")
                i += 1
                if old_working:
                    old_working_pips = [x[1] for x in old_working]
                    if pip in old_working_pips:
                        idx = old_working_pips.index(pip)
                        working.append((t, pip, old_working[idx][2]))
                        continue
                working.append((t, pip, NOT_ANON_FLAG))
        print()
        print(f"Saving Proxies to {WORKING_JSON_FH.path}")
        working.sort(key=lambda x: x[0])
        WORKING_JSON_FH.write(json.dumps(working))

    while True:
        proxies = open(proxy_file, "r").read().split("\n")
        n_proxies = len(proxies)
        threads = []
        consume_thread = Thread(target=consume_queue)
        consume_thread.daemon = False
        consume_thread.start()
        for proxy in proxies:
            thread = Thread(target=check_proxy, args=(proxy.strip(),))
            thread.daemon = False
            threads.append(thread)
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        stop_event.set()
        consume_thread.join()
        stop_event.clear()


def start_anon_checking():
    time.sleep(2)
    qu = Queue()
    stop_event = Event()
    proxies = None
    n_proxies = 0

    def check_anon(pip: str):
        try:
            req = get(ANON_CHECK_URL, proxy_data={"http": pip, "https": pip})
            if not req:
                return
            text = req.read().decode("utf-8")
            if "X-Forwarded-For" in text:
                return
        except Exception as e:
            print(e)
            return
        qu.put(pip)

    def consume_queue():
        good = []
        while True:
            if stop_event.is_set():
                break
            if not qu.empty():
                good.append(qu.get(block=False))
            time.sleep(0.01)
        working = []
        for tt, proxy, type in proxies:
            if proxy in good:
                working.append((tt, proxy, ANON_FLAG))
            else:
                working.append((tt, proxy, NOT_ANON_FLAG))
        working.sort(key=lambda x: x[0])
        # print("Writing anonymity infos to file")
        WORKING_JSON_FH.write(json.dumps(working))

    while True:
        working_url = f"http://127.0.0.1:{PORT}/api/working?type=all"
        req = get(working_url)
        if not req:
            time.sleep(1)
            continue
        _read = req.read().decode("utf-8")
        try:
            proxies = json.loads(_read)
        except json.JSONDecodeError:
            # print(_read)
            time.sleep(1)
            continue
        print()
        print("Running anonymity checks")
        n_proxies = len(proxies)
        threads = []
        for i in range(n_proxies):
            tt, proxy, type = proxies[i]
            t = Thread(target=check_anon, args=(proxy,))
            t.daemon = False
            threads.append(t)
        for t in threads:
            t.start()

        consume_thread = Thread(target=consume_queue, args=())
        consume_thread.start()

        for t in threads:
            t.join()
        stop_event.set()
        consume_thread.join()
        stop_event.clear()


def toggle_checking():
    global CHECKING_STARTED, CHECKING_THREAD, ANONCHECKING_THREAD
    if CHECKING_STARTED:
        CHECKING_THREAD.join()
        CHECKING_THREAD = None
        ANONCHECKING_THREAD.join()
        ANONCHECKING_THREAD = None
    else:
        CHECKING_THREAD = Thread(target=start_checking)
        CHECKING_THREAD.start()
        ANONCHECKING_THREAD = Thread(target=start_anon_checking)
        ANONCHECKING_THREAD.start()
    CHECKING_STARTED = not CHECKING_STARTED
    return CHECKING_STARTED


def server(host: str):
    from flask import Flask, jsonify, request, abort, redirect

    cli = sys.modules["flask.cli"]
    cli.show_server_banner = lambda *x: None
    app = Flask(__name__)

    @app.route("/", methods=["GET", "POST"])
    def index():
        if request.method == "GET":
            global CHECKING_STARTED
            return f"<form action='/', method='post'><input style='height: 50%; width: 50%; font: small-caps bold 1000%/200% monospace;' type='submit' value='running={CHECKING_STARTED}'></form>"
        elif request.method == "POST":
            status = toggle_checking()
            return redirect("/")
        else:
            return abort(400)

    @app.route("/api/working")
    def working():
        _read = WORKING_JSON_FH.read()
        try:
            working_json = json.loads(_read)
        except JSONDecodeError:
            return "No data exists, Retry later"

        types = ["all", "anon"]
        type = request.args.get("type")

        if type == "all" or not type:
            pass
        elif type == "anon":
            working_json = [x for x in working_json if x[2] == "anon"]
        else:
            return f"Invalid type, please use type from {types}"
        return jsonify(working_json)

    @app.route("/api/working/")
    def red_working():
        return redirect("/api/working")

    @app.route("/api/headers")
    def hedaers():
        return str(request.headers)

    @app.route("/api/headers/")
    def red_headers():
        return redirect("/api/headers")

    import logging

    logging.basicConfig(filename="flask.log", level=logging.DEBUG)

    def console():
        time.sleep(2)
        print(open("flask.log", "r").read().split("\n")[-2], flush=True)

    Thread(target=console).start()
    app.run(host, PORT)


parser = argparse.ArgumentParser()
parser.add_argument("-ho", "--host", type=str, help="Hostname", default="0.0.0.0")
parser.add_argument("-p", "--port", type=int, help="Port", default=4000)
# parser.add_argument("-l", '--local', help="Local Anonymity checking", action="store_true")
args = parser.parse_args()
PORT = args.port
ANON_CHECK_URL = f"http://{CHECK_PIP}/api/headers"
WORKING_JSON_FH = FileHandler.create("working.json")
server(args.host)
