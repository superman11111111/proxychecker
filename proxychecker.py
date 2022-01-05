import argparse
import re
import sys
import urllib.request
import socket
from threading import Thread, Event
from queue import Queue
import time
import json
import os

# Settings
PUBLIC_IP = ""  # Public IP of the server running this script, I am not automating this for security reasons
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
HTTP_ERRORS = ""
# HTTP_ERRORS = "error.log" # Uncomment to log HTTP errors
if HTTP_ERRORS:
    if not os.path.isfile(HTTP_ERRORS):
        open(HTTP_ERRORS, "w").write("")

socket.setdefaulttimeout(TIMEOUT)


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
        working = []
        i = 0
        while True:
            if stop_event.is_set():
                break
            if not qu.empty():
                t, pip = qu.get(block=False)
                _print = f"{i}/{n_proxies} {round(t, 4)} {pip}  "
                print(f"\r{_print}{(50 - len(_print))*' '}", end="")
                working.append((t, pip, NOT_ANON_FLAG))
                i += 1
            time.sleep(0.01)
        print()
        print("Saving Proxies to working_info.json")
        working.sort(key=lambda x: x[0])
        working_json = json.dumps(working)
        f = open("working_info.json", "w")
        f.write(working_json)
        f.close()

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
    while not os.path.isfile("working_info.json"):
        time.sleep(1)
    print("Starting anonymity checks")
    qu = Queue()
    stop_event = Event()
    n_proxies = 0

    def check_anon(pip: str):
        try:
            # start_t = time.time()
            # print(ANON_CHECK_URL)
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
        print(good)
        f = open("working_info.json", "r")
        _r = f.read()
        f.close()
        working_proxies = json.loads(_r)
        working_info = []
        for tt, proxy, _ in working_proxies:
            if proxy in good:
                working_info.append((tt, proxy, "anon"))
            else:
                working_info.append((tt, proxy, "not_anon"))
        working_info.sort(key=lambda x: x[0])
        print("Writing anonymity infos to file")
        f = open("working_info.json", "w")
        f.write(json.dumps(working_info))
        f.close()

    while True:
        working_url = f"http://127.0.0.1:{PORT}/api/working?type=all"
        req = get(working_url)
        if not req:
            print(f"No working data from {working_url}, retrying in 1")
            time.sleep(1)
            continue
        _read = req.read().decode("utf-8")
        try:
            proxies = json.loads(_read)
        except json.JSONDecodeError:
            # print(_read)
            continue
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
        n = request.args.get("n")
        if n:
            try:
                n = int(n)
            except:
                return "Wrong parameter n (use int)"
        if not os.path.isfile("working_info.json"):
            return "No data exists, Retry later"

        types = ["all", "anon"]
        type = request.args.get("type")

        if type not in types:
            return f"Invalid type, please use type from {types}"

        f = open("working_info.json", "r")
        _read = f.read()
        f.close()
        working_json = json.loads(_read)
        if type == "anon":
            working_json = [x for x in working_json if x[2] == "anon"]
        if n:
            return jsonify(working_json[:n])
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

    # print(f" * Running Flask on http://{host}:{port}")
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
args = parser.parse_args()
PORT = args.port
ANON_CHECK_URL = f"http://{PUBLIC_IP}:{PORT}/api/headers"
server(args.host)
