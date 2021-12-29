import argparse
import sys
import urllib.request
import socket
from threading import Thread, Event
from queue import Queue
import time
import json
import os

socket.setdefaulttimeout(30)


def check_proxy(pip, out_queue: Queue):
    try:
        proxy_handler = urllib.request.ProxyHandler({'https': pip})
        opener = urllib.request.build_opener(proxy_handler)
        opener.addheaders = [('User-agent', 'Mozilla/5.0')]
        urllib.request.install_opener(opener)
        start = time.time()
        sock = urllib.request.urlopen('https://www.myip.com/')
        out_queue.put((time.time() - start, pip))
    except urllib.error.HTTPError as e:
        return e
    except Exception as detail:
        return detail
    return 0


def consume_queue(proxies: list, q: Queue, stop_event: Event):
    working = []
    import time
    l = len(proxies)
    i = 0
    while True:
        # print(stop_event.is_set())
        if stop_event.is_set():
            break
        if not q.empty():
            t, pip = q.get(block=False)
            print(f'\r{i}/{l} {t} {pip}  ', end='')
            working.append((t, pip))
            i += 1
        time.sleep(.01)
    import json
    print()
    print('Saving Proxies')
    sort = sorted(working, key=lambda x: x[0])
    open('working.json', 'w').write(json.dumps(sort))


# Example run : echo -ne "192.168.1.1:231\n192.168.1.2:231" | python proxy_checkpy3-async.py
# proxies = sys.stdin.readlines()
# proxies = input("[proxies]\n").split('\n')


def start_checking(proxy_file='proxies.txt'):
    time.sleep(2)
    print()
    q = Queue()
    stop_event = Event()
    while True:
        proxies = open(proxy_file, 'r').read().split('\n')
        threads = []
        consume_thread = Thread(target=consume_queue,
                                args=(proxies, q, stop_event, ))
        consume_thread.daemon = False
        consume_thread.start()

        for proxy in proxies:
            thread = Thread(target=check_proxy, args=(proxy.strip(), q, ))
            thread.daemon = False
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()
        stop_event.set()
        consume_thread.join()
        stop_event.clear()
        # print('Waiting 1 minutes')
        # time.sleep(60)


def server(host: str, port: int):
    from flask import Flask, jsonify, request
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)

    app = Flask(__name__)

    @app.route("/")
    def index():
        return "<p>Hello, World!</p>"

    @app.route("/api/working")
    def working():
        n = request.args.get('n')
        # print(n)
        # os.path.getmtime('working.json')
        if n:
            try:
                n = int(n)
            except:
                return "Wrong parameter n (use int)"
            return jsonify(json.loads(open('working.json', 'r').read())[:n])
        return jsonify(json.loads(open('working.json', 'r').read()))

    print(f' * Running Flask on http://{host}:{port}')
    app.run(host, port)


parser = argparse.ArgumentParser()
parser.add_argument('-ho', '--host', type=str,
                    help='Hostname', default='127.0.0.1')
parser.add_argument('-p', '--port', type=int, help='Port', default=4001)

args = parser.parse_args()
check_thread = Thread(target=start_checking)
check_thread.start()
server(args.host, args.port)
check_thread.join()
