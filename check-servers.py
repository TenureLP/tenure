"""Asks the landing and app servers for their pages and for the source beside them.

    python3 check-servers.py

Both servers sit next to source, so the only thing between that source and the internet is their
allowlist. This asks for both, over GET and HEAD. Standard library only; run by check.sh and by CI.
"""


def landing():
    import sys, threading, urllib.request, urllib.error
    sys.path.insert(0, "landing")
    from http.server import ThreadingHTTPServer
    from functools import partial
    sys.modules.pop('server', None); sys.modules.pop('dev_server', None)
    import server
    server.ProdHandler.log_message = lambda *a: None

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(server.ProdHandler, directory=server.HERE))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]

    def status(path, method="GET"):
        try:
            with urllib.request.urlopen(urllib.request.Request(base + path, method=method)) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, b""

    for path in ("/", "/olanas", "/olanas.html", "/assets/site.css", "/assets/logo-nav.svg"):
        assert status(path)[0] == 200, path
    code, headers, body = status("/")
    assert "script-src 'none'" in headers["content-security-policy"]
    assert b"<script" not in body and b'style="' not in body, "the policy forbids inline script and style"
    assert b"<script" not in status("/olanas")[2] and b'style="' not in status("/olanas")[2]
    for path in ("/server.py", "/dev_server.py", "/read_waitlist.py", "/README.md", "/Dockerfile",
                 "/api/waitlist", "/assets/../server.py", "/assets/%2e%2e/server.py"):
        for method in ("GET", "HEAD"):
            assert status(path, method)[0] == 404, (method, path)
    httpd.shutdown()
    print("   two pages, no script, no inline style; source refused on GET and HEAD")


def app():
    import sys, threading, urllib.request, urllib.error
    sys.path.insert(0, "app")
    from http.server import ThreadingHTTPServer
    from functools import partial
    sys.modules.pop('server', None); sys.modules.pop('dev_server', None)
    import server
    server.ProdHandler.log_message = lambda *a: None  # the 404s are the point, not news

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(server.ProdHandler, directory=server.HERE))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]

    def status(path, method="GET"):
        try:
            with urllib.request.urlopen(urllib.request.Request(base + path, method=method)) as r:
                r.read()  # read to the end, or the server logs a broken pipe for every file
                return r.status, r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.headers

    for path in ("/", "/index.html", "/app.js", "/theme.js", "/config.js", "/assets/app.css", "/assets/logo-mark-small.svg"):
        code, headers = status(path)
        assert code == 200, (path, code)
    code, headers = status("/")
    csp = headers["content-security-policy"]
    assert "frame-ancestors 'none'" in csp and "script-src 'self'" in csp, csp
    assert "https://rpc.mainnet.chain.robinhood.com" in csp, "config.js origins missing from connect-src"
    for path in ("/server.py", "/dev_server.py", "/devchain.sh", "/test/eth.test.js", "/README.md",
                 "/Dockerfile", "/assets/../server.py", "/assets/%2e%2e/server.py"):
        for method in ("GET", "HEAD"):
            assert status(path, method)[0] == 404, (method, path)
    httpd.shutdown()
    print("   page served with its headers; source refused on GET and HEAD")


if __name__ == "__main__":
    landing()
    app()
