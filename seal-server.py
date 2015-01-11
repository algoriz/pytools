#!/usr/bin/python

import time
import datetime
import socket
import select
import threading
import urlparse

# Global log level
# 0: critical errors
# 1: warnings
# 2: URL access record
# 3: general information
LOG_LEVEL = 3

# Log device guard
_log_lock = threading.Event()
_log_lock.set()


def log(msg, prefix="[LOG]", level=3):
    """ Generates a log message. """
    if level > LOG_LEVEL:
        return
    _log_lock.wait()
    t = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(prefix + " [" + t + "] " + msg)
    _log_lock.set()


def hit(url):
    log(url, prefix="[URL]", level=2)


def warn(msg):
    """ Generates a warning message. """
    log(msg, prefix="[WARN]", level=1)


def error(msg):
    """ Generates an error message. """
    log(msg, prefix="[ERROR]", level=0)


def close_nothrow(sock):
    if sock is None:
        return
    try:
        sock.close()
    except Exception:
        pass


def forward_message_body(dst, msg, src):
    length = msg.get_int("Content-Length", -1)
    if length != -1:
        dst.copy_bytes(src, length)
        return True

    # Multiple Transfer-Encoding's may be applied, but "chunked" must be the final one.
    # See RFC7230 Section 3.3.1
    encoding = msg.get("Transfer-Encoding")
    if encoding.lower().endswith("chunked"):
        dst.copy_chunks(src)
        return True
    return False


class IOException(Exception):
    def __init__(self, reason="Generic Error"):
        Exception.__init__(self, reason)
        self.reason = reason


class HttpHeaders:
    def __init__(self):
        self.keys = []
        self.values = []

    def __len__(self):
        return len(self.keys)

    def __contains__(self, item):
        return isinstance(item, str) and self.find(item) != -1

    def __str__(self):
        s = ""
        for i in range(0, len(self.keys)):
            s += self.keys[i] + ": " + self.values[i] + "\r\n"
        return s

    def __getitem__(self, item):
        val = self.get(item)
        if val is None:
            raise IndexError()
        return val

    def __setitem__(self, key, value):
        return self.set(key, value)

    def get(self, key, default_value=None):
        key = key.lower()
        for i in range(0, len(self.keys)):
            if key == self.keys[i].lower():
                return self.values[i]
        return default_value

    def getall(self, key):
        """ Get all header values associated with the specified key.
        :return: A list of values that are associated with the key
        """
        values = []
        key = key.lower()
        for i in range(0, len(self.keys)):
            if key == self.keys[i].lower():
                values.append(self.values[i])
        return values

    def find(self, key, start=0):
        key = key.lower()
        if start > len(self.keys):
            # out of range
            return -1
        for i in range(start, len(self.keys)):
            if key == self.keys[i].lower():
                return i
        return -1

    def append(self, key, value):
        self.keys.append(key)
        self.values.append(value)

    def set(self, key, value):
        i = self.find(key)
        if i != -1:
            self.values[i] = value
            # remove other values
            self.delete(key, i + 1)
        else:
            self.append(key, value)

    def delete(self, key, start=0):
        i = self.find(key, start)
        while i != -1:
            self.keys.pop(i)
            self.values.pop(i)
            i = self.find(key, i)

    def pop(self, i):
        self.keys.pop(i)
        self.values.pop(i)

    def at(self, i):
        return self.keys[i], self.values[i]


class HttpMessage:
    """ Represents an HTTP message. """

    def __init__(self):
        self.start_line = ""
        self.headers = HttpHeaders()
        self.body = ""

        """ Message body transfer status
          True : body not received yet
          False: body ready
        """
        self.body_pending = False

    def __str__(self):
        s = self.start_line + "\r\n"
        s += str(self.headers)
        s += "\r\n"
        if self.body is not None:
            s += self.body
        return s

    def add(self, key, val):
        self.headers.append(key, val)

    def add_header(self, keyval):
        self.headers.append(keyval[0], keyval[1])

    def add_header_line(self, line):
        p = line.find(":")
        k = line[:p].strip(" \t")
        v = line[p + 1:].strip(" \t")
        return self.headers.append(k, v)

    def append(self, data):
        self.body += data

    def get(self, key, default_value=None):
        """ Get the value associated with the key. """
        return self.headers.get(key, default_value)

    def get_int(self, key, default_value=0):
        """ Get the integer value associated with the key. """
        val = self.headers.get(key)
        if val is not None:
            return int(val)
        return default_value

    def get_float(self, key, default_value=0.0):
        """ Get the float value associated with the key. """
        val = self.headers.get(key)
        if val is not None:
            return float(val)
        return default_value

    def has(self, key):
        """ Test whether the specified key exists.
        :return: True if the specified key exists, otherwise returns False
        """
        return self.headers.find(key) != -1

    def has_keyval(self, key, value):
        """ Test whether the specified key/value pair exists.
        :return: True if the specified key/value pair exists, otherwise returns False
        """
        return self.headers.get(key) == value


class HttpRequest(HttpMessage):
    def __init__(self):
        HttpMessage.__init__(self)

    def __str__(self):
        return HttpMessage.__str__(self)

    def set_request(self, target, method="GET", version="HTTP/1.1"):
        self.start_line = method + " " + target + " " + version

    def set_request_line(self, line):
        self.start_line = line

    def method(self):
        return self.start_line.split(" ", 1)[0]

    def target(self):
        a = self.start_line.find(" ")
        b = self.start_line.rfind(" ")
        return self.start_line[a+1:b].strip(" \t")

    def version(self):
        b = self.start_line.rfind(" ")
        return self.start_line[b+1:].strip(" \t")


class HttpResponse(HttpMessage):
    def __init__(self):
        HttpMessage.__init__(self)
        pass

    def set_status(self, code, phrase, version="HTTP/1.1"):
        self.start_line = version + " " + code + " " + phrase

    def set_status_line(self, line):
        self.start_line = line

    def version(self):
        a = self.start_line.find(" ")
        return self.start_line[:a]

    def code(self):
        a = self.start_line.find(" ")
        a = ++a
        while self.start_line[a] == ' ':
            a = ++a
        b = self.start_line.find(" ", a)
        return int(self.start_line[a:b])

    def phrase(self):
        a = self.start_line.find(" ")
        a = ++a
        while self.start_line[a] == ' ':
            a = ++a
        b = self.start_line.find(" ", a)
        return self.start_line[b+1:].strip(" \t")


class HttpInputStream:
    """ An HttpInputStream represents an incoming HTTP data flow, which
     can be either HTTP request stream for an HTTP server or an HTTP
     response stream for an HTTP client.
    """
    def __init__(self, conn=None):
        self.conn = conn                # socket connection
        self.rdbuf = ""                 # read buffer
        self.maxrdbuf = 128 * 1024      # max size of read buffer, 128KB by default.

    def attach(self, conn):
        self.conn = conn
        self.rdbuf = ""

    def wait(self):
        """ Wait for data input.
        This method does nothing and returns immediately if the read buffer is not empty.
        """
        if len(self.rdbuf):
            return
        try:
            self.rdbuf = self.conn.recv(self.maxrdbuf)
        except:
            raise IOException("Connection reset.")
        if len(self.rdbuf) == 0:
            raise IOException("Connection closed.")

    def read_some(self, max):
        self.wait()
        r = self.rdbuf[:max]
        self.rdbuf = self.rdbuf[max:]
        return r

    def read(self, n):
        """ Read n bytes from the stream.
        :param n: Number of bytes to read
        :return: A string that contains the data read.
        """
        r = ""
        while len(r) < n:
            self.wait()

            a = n - len(r)
            if a < len(self.rdbuf):
                a = len(self.rdbuf)
            r += self.rdbuf[:a]
            self.rdbuf = self.rdbuf[a:]
        return r

    def read_line(self):
        """ Read a line from the stream using CRLF as line ending.
        :return: A string that contains the data read.
        """
        r = ""
        crlf_pos = -1
        while crlf_pos == -1:
            if len(r) >= self.maxrdbuf:
                raise IOException("read_line run out of buffer")

            self.wait()
            crlf_pos = self.rdbuf.find("\r\n")
            if crlf_pos != -1:
                r += self.rdbuf[:crlf_pos]
                self.rdbuf = self.rdbuf[crlf_pos + 2:]
            else:
                r += self.rdbuf
                self.rdbuf = ""
        return r

    def read_message(self, m):
        """ Read an HTTP message from stream.
        An IOException is raised if the size of the header part of incoming message is larger than maxrdbuf.
        Only when the incoming message carries a Content-Length header and Content-Length <= maxrdbuf, the message body
         will be fully copied to body field.
        Otherwise, body_pending field will be set True and the message body should be read manually later.
        """
        m.start_line = self.read_line()

        prev_line = ""
        curr_line = self.read_line()
        while len(curr_line):
            if curr_line[0] in " \t":
                # folded header field value
                prev_line += curr_line.strip(" \t")
            else:
                if len(prev_line):
                    m.add_header_line(prev_line)
                prev_line = curr_line
            curr_line = self.read_line()

        if len(prev_line):
            m.add_header_line(prev_line)

        # Read message body if the size of body is explicitly told and is under buffer size limit
        m.body = ""
        body_size = m.get_int("Content-Length", -1)
        if 0 <= body_size <= self.maxrdbuf:
            m.body = self.read(body_size)
            m.body_pending = False
        else:
            # To be determined
            m.body_pending = True
        return m

    def read_request(self):
        r = HttpRequest()
        self.read_message(r)
        if r.method() in ["GET", "HEAD", "DELETE", "CONNECT", "TRACE"]:
            # Those method may not has payload
            r.body_pending = False
        else:  # POST, PUT, OPTIONS
            r.body_pending = True
        return r

    def read_response(self):
        r = HttpResponse()
        self.read_message(r)
        return r

    def close(self):
        try:
            self.conn.shutdown(socket.SHUT_RD)
        except Exception:
            pass


class HttpOutputStream:
    def __init__(self, conn):
        self.conn = conn

    def copy_bytes(self, src, count):
        """ Copy count bytes from src to output. """
        copied = 0
        while copied != count:
            d = src.read_some(count-copied)
            self.write(d)
            copied += len(d)

    def copy_chunks(self, src):
        """ Copy chunks from src to output. See RFC7320 Section 4.1 """
        while True:
            chunk_header = src.read_line()
            chunk_size = int(chunk_header.strip(" \t").split(' ', 1)[0], 16)
            if chunk_size <= 0:
                break
            self.write(chunk_header + "\r\n")
            self.copy_bytes(src, chunk_size + 2)
        self.write("0\r\n")

        # trailer-part
        trailer_line = src.read_line()
        while len(trailer_line):
            self.write(trailer_line + "\r\n")
            trailer_line = src.read_line()
        self.write("\r\n")

    def write(self, data):
        written = 0
        while written != len(data):
            count = self.conn.send(data[written:])
            if count <= 0:
                raise IOException("Connection closed before write complete.")
            written += count

    def close(self):
        try:
            self.conn.shutdown(socket.SHUT_WR)
        except Exception:
            pass


class SocketTunnel:
    def __init__(self, peers):
        """
        :param peers: a pair of sockets to create the tunnel
        """
        self.peers = peers

    def run(self):
        while True:
            r, w, x = select.select(self.peers, [], self.peers)
            if len(r):
                self._forward(r[0])
            if len(r) == 2:
                self._forward(r[1])
            if len(x):
                break
        # Close the tunnel by raising an IOException
        raise IOException("Socket tunnel closed.")

    def _forward(self, src):
        dst = self.peers[0]
        if src == self.peers[0]:
            dst = self.peers[1]
        d = src.recv(16 * 1024)
        dst.sendall(d)


class HttpProxyHandler:
    MAX_HEADER = 128 * 1024
    KEEP_ALIVE_DEFAULT = True

    def __init__(self, s):
        self.client_conn = s
        self.client_input = HttpInputStream(s)
        self.client_output = HttpOutputStream(s)
        self.remote_addr = None
        self.remote_conn = None
        self.remote_input = None
        self.remote_output = None

    def run(self):
        keep_alive = True
        try:
            while keep_alive:
                r = self.client_input.read_request()

                keep_alive = HttpProxyHandler.KEEP_ALIVE_DEFAULT
                connspec = r.get("Proxy-Connection")
                if connspec is not None:
                    keep_alive = connspec.lower() == "keep-alive"

                self.handle_request(r)
        except IOException, e:
            log(e.reason, level=5)
        except Exception:
            # TODO handle exceptions here
            pass
        finally:
            self.final_clean()

    def close_remote(self):
        if self.remote_conn is None:
            return
        if self.remote_input is not None:
            self.remote_input.close()
            self.remote_input = None
        if self.remote_output is not None:
            self.remote_output.close()
            self.remote_output = None
        close_nothrow(self.remote_conn)
        self.remote_conn = None
        self.remote_addr = None

    def final_clean(self):
        self.client_input.close()
        self.client_output.close()
        close_nothrow(self.client_conn)
        self.close_remote()

    def handle_request(self, request):
        method = request.method()
        if method == "CONNECT":
            return self.handle_CONNECT(request)
        elif method not in ["GET", "HEAD", "POST", "PUT", "DELETE", "TRACE", "OPTIONS"]:
            raise IOException("Unknown method: " + method)

        original_url = request.target()
        if method == "GET":
            hit(original_url)

        urlparts = urlparse.urlparse(original_url)
        host = urlparts.netloc
        port = 80
        if ':' in urlparts.netloc:
            p = urlparts.netloc.find(':')
            host = urlparts.netloc[:p]
            port = int(urlparts.netloc[p + 1:])

        target = urlparts.path
        if len(urlparts.query):
            target += "?" + urlparts.query
        fwd = HttpRequest()
        fwd.set_request(target, method)

        # Add Host field if needed
        if not request.has("Host"):
            fwd.add("Host", urlparts.netloc)

        for i in range(0, len(request.headers)):
            if request.headers.keys[i].lower().startswith("proxy-"):
                # No forward proxy specific headers
                continue
            fwd.add_header(request.headers.at(i))

        fwd.body = request.body
        fwd.body_pending = request.body_pending

        # forward the request to remote server
        self.send_with_retry(host, port, str(fwd))
        if method == "POST" and fwd.body_pending:
            # Only POST messages may carry a message body
            forward_message_body(self.remote_output, fwd, self.client_input)

        # forward the response to proxy client
        resp = self.remote_input.read_response()
        self.client_output.write(str(resp))
        if resp.body_pending:
            forward_message_body(self.client_output, resp, self.remote_input)

    def handle_CONNECT(self, request):
        a = request.start_line.find(' ')
        b = request.start_line.rfind(' ')
        c = request.start_line.find(':', a+1, b)
        host = request.start_line[a:c].strip(" \t")
        port = int(request.start_line[c+1:b].strip(" \t"))
        if not len(host) or port <= 0:
            raise IOException("Bad CONNECT request target")

        paddr, pport = self.client_conn.getpeername()
        log("%s:%d <--> %s:%d" % (paddr, pport, host, port))

        try:
            if self.remote_addr != (host, port):
                self.close_remote()
                self.remote_conn = socket.create_connection((host, port))
        except Exception:
            self.client_output.write("HTTP/1.1 503 Service Unavailable\r\nHost: seal\r\n\r\n")
            raise IOException("Failed to create tunnel %s:%d" % (host, port))

        self.client_output.write("HTTP/1.1 200 OK\r\nHost: seal\r\n\r\n")
        fwd = SocketTunnel((self.client_conn, self.remote_conn))
        fwd.run()

    def send_with_retry(self, host, port, data, retries=3):
        # HTTP is a stateless protocol, thus we could reuse the connection
        # However, since the kept old connection may have been closed by remote server, we
        # have to do some retry
        retry_count = 0
        while retry_count < retries:
            try:
                if self.remote_addr != (host, port):
                    self.close_remote()
                    # connect to the new remote server
                    self.remote_addr = (host, port)
                    self.remote_conn = socket.create_connection((host, port))
                    self.remote_input = HttpInputStream(self.remote_conn)
                    self.remote_output = HttpOutputStream(self.remote_conn)
                self.remote_output.write(data)
                break
            except (IOException, Exception):
                # connection seems broken
                self.close_remote()
                retry_count += 1
        if retry_count >= retries:
            log("Couldn't connect %d:%d" % (host, port))
            raise IOException("Can't connect to remote server: %s:%d" % (host, port))


class ThreadingServer:
    def __init__(self, address, handler):
        self.address = address
        self.backlog = 50
        self.handler = handler

    def run(self):
        s = None
        try:
            s = socket.socket()
            s.bind(self.address)
            s.listen(self.backlog)
            log("Starting proxy service at %s:%d" % self.address)
            while True:
                handler = self.handler(s.accept()[0])
                threading.Thread(target=handler.run).start()
        except Exception:
            error("Caught an unhandled exception, exit service loop...")
        finally:
            s.close()


def main():
    addr = "0.0.0.0"
    port = 8085
    restart_time = 3
    restart_time_upper_bound = 30
    while True:
        server = ThreadingServer((addr, port), HttpProxyHandler)
        server.run()

        if restart_time > restart_time_upper_bound:
            error("Too many errors, stop trying to restart service. BYE BYE.")
            exit(1)

        warn("Service down!!! Restarting service after %d seconds." % restart_time)
        time.sleep(restart_time)
        restart_time += 3
    exit(0)


if __name__ == "__main__":
    main()
