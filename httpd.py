#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import getopt
import os
import asyncore
import asynchat
import platform
import re
import socket
import multiprocessing
import logging
from time import strftime, gmtime


class HTTPRequest(object):
    __slots__ = ['headers', 'uri', 'http_version', 'body']

    def __init__(self, headers, uri="", http_version=1.1, body=None):
        self.headers = headers
        self.uri = uri
        self.http_version = http_version
        self.body = body

    def get_params(self, query=None):
        pass


class GETRequest(HTTPRequest):

    def __init__(self, headers, uri="", http_version=1.0, body=None):
        super(GETRequest, self).__init__(headers, uri=uri, http_version=http_version, body=body)
        self.method = "GET"

    def get_params(self, query=None):
        if not query:
            return {}
        parameters = {}
        key_value_list = re.split(r'[&#;$]', query)
        for pair in key_value_list:
            key, value = pair.split("=")
            parameters[key] = value
        return parameters


class HEADRequest(HTTPRequest):

    def __init__(self, headers, uri="", http_version=1.0, body=None):
        super(HEADRequest, self).__init__(headers, uri=uri, http_version=http_version, body=body)
        self.method = "HEAD"


class POSTRequest(HTTPRequest):

    def __init__(self, headers, uri="", http_version=1.0, body=None):
        super(POSTRequest, self).__init__(headers, uri=uri, http_version=http_version, body=body)
        self.method = "POST"

    def get_params(self, query=None):
        return self.body


class ContentProducer(object):

    def __init__(self, file_descriptor, chunk_size=4096):
        self.fd = file_descriptor
        self.chunk_size = chunk_size

    def more(self):
        if self.fd:
            data = self.fd.read(self.chunk_size)
            if data:
                return data
            self.fd.close()
            self.fd = None
        return ""


class HTTPHandler(asynchat.async_chat):

    def __init__(self, server, sock, addr):
        asynchat.async_chat.__init__(self, sock=sock)
        self.server = server
        self.addr = addr
        self.set_terminator("\r\n\r\n")
        self.max_buffer_size = 256
        self.ibuffer = b""

    def collect_incoming_data(self, data):
        if len(self.ibuffer) > self.max_buffer_size:
            self.ibuffer = b""
        self.ibuffer += data

    def found_terminator(self):
        http_request = self.server.parse_request(self.ibuffer)
        self.server.handle_request(self, http_request)

    def send_response(self, st_line, **response_headers):
        self.push(st_line + "\r\n")
        for hdr, hdr_v in response_headers.items():
            self.push(str(hdr) + ": " + str(hdr_v) + "\r\n")
        self.push("\r\n")


class HTTPServer(asyncore.dispatcher):

    index = "index.html"

    __encoded_chars = {"%20": ' ', "%21": '!', "%22": "\"", "%23": '#', "%24": '$', "%25": '%', "%26": '&',
                       "%27": '\'', "%28": '(', "%29": ')', "%30": "0", "%31": "1", "%32": "2", "%33": "3",
                       "%34": '4', "%35": '5', "%36": '6', "%37": '7', "%38": '8', "%39": '9', "%40": '@',
                       "%41": 'A', "%42": 'B', "%43": 'C', "%44": 'D', "%45": 'E', "%46": 'F', "%47": 'G',
                       "%48": 'H', "%49": 'I',  "%4A": 'J', "%4B": 'K', "%4C": 'L', "%4D": 'M', "%4E": 'N',
                       "%4F": 'O', "%50": 'P', "%51": 'Q', "%52": 'R', "%53": 'S', "%54": 'T', "%55": 'U',
                       "%56": 'V', "%57": 'W', "%58": 'X', "%59": 'Y', "%5A": 'Z', "%5B": '[', "%5C": '\\',
                       "%5D": ']', "%5E": '^', "%5F": '_', "%60": ']', "%61": 'a', "%62": 'b', "%63": 'c',
                       "%64": 'd', "%65": 'e', "%66": 'f', "%67": 'g', "%68": 'h', "%69": 'i', "%6A": 'j',
                       "%6B": 'k', "%6C": 'l', "%6D": 'm', "%6E": 'n', "%6F": 'o', "%70": 'p', "%71": 'q',
                       "%72": 'r', "%73": 's', "%74": 't', "%75": 'u', "%76": 'v', "%77": 'w', "%78": 'x',
                       "%79": 'y', "7A": 'z', "7B": '{', "7C": '|', "7D": '}', "7E": '~', "7F": ' ',
                       "%2B": '+', "%2C": ',', "%2D": '-', "%2E": '.',  "%2F": '/', "%3A": ':', "%3B": ';',
                       "%3C": '<', "%3D": '=', "%3E": '>', "%3F": '?',  "+": ' '}
    __content_types = {"html": "text/html", "css": "text/css", "js": "application/javascript",
                       "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                       "gif": "image/gif", "swf": "application/x-shockwave-flash"}

    def __init__(self, address="", port=8080, document_root="/home/artem", forbidden=""):
        asyncore.dispatcher.__init__(self)
        self.address = address
        self.port = port
        self.document_root = document_root
        self.forbidden_methods = forbidden.split(',')
        if self.document_root[-1:] == '/':
            self.document_root = self.document_root[:-1]

        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.bind((self.address, self.port))
        self.listen(5)
        log.debug("Listening on address %s:%s", address, port)

    def serve_forever(self):
        try:
            asyncore.loop(timeout=60, use_poll=True)
        except KeyboardInterrupt:
            log.debug("Close worker")
            asyncore.close_all()
        finally:

            self.close()

    def handle_accept(self):
        conn, addr = self.accept()
        if conn is not None and addr is not None:
            HTTPHandler(self, sock=conn, addr=addr)

    def parse_request(self, request):
        """returns object of HTTPRequest as certain data structure"""
        if not request:
            return None

        http_requests = {
            "HEAD": HEADRequest,
            "GET": GETRequest,
            "POST": POSTRequest
        }

        def parse_request_line(request_line_):
            method_, uri_, http_version_ = request_line_.split(" ")
            return method_, uri_, http_version_

        request_lines = request.split("\r\n")
        request_line = request_lines[0]
        method, uri, http_version = parse_request_line(request_line)
        headers = request_lines[1:]
        body = ""
        if method in http_requests:
            return http_requests[method](headers, uri, http_version, body)
        else:
            return None

    def handle_request(self, channel, http_request):
        """sends response via given channel (HTTPHandler)"""
        send_content = False
        content = None
        status_line = "HTTP/1.0 405 Method Not Allowed"
        response_headers = {
                "Host": socket.gethostname(), "Date": HTTPServer.get_date(),
                "Server": HTTPServer.get_server(), "Connection": "close",
            }
        try:
            if not http_request:
                return
            os_path, parameters = self.uri_resolve(http_request)

            if os_path is "Forbidden location":
                status_line = "HTTP/1.0 403 Forbidden"
                return

            if http_request.method in self.forbidden_methods:
                status_line = "HTTP/1.0 405 Method Not Allowed"
                return

            log.debug(os_path)
            content = open(os_path, "rb")
        except IOError:
            status_line = "HTTP/1.0 404 Not Found"
        else:
            status_line = "HTTP/1.0 200 OK"
            response_headers["Content-Type"] = HTTPServer.detect_content_type(os_path)
            response_headers["Content-Length"] = os.path.getsize(os_path)

            if http_request.method is not "HEAD":
                send_content = True
        finally:
            channel.send_response(status_line, **response_headers)
            if send_content:
                channel.push_with_producer(ContentProducer(content))
            channel.close_when_done()

    def uri_resolve(self, http_request):
        """returns location of requested resource on server and given parameters of request"""
        uri_parts = http_request.uri.split('?') + [None]

        if '' in uri_parts:
            uri_parts = filter(lambda a: a != '', uri_parts)

        parameters = http_request.get_params(uri_parts[1])

        resource_location = self.decode_uri(HTTPServer.normalize_uri(uri_parts[0]))

        if resource_location.find("../") != -1:
            return "Forbidden location", parameters

        if resource_location[-1:] == '/':
            resource_location += HTTPServer.index

        return self.document_root + resource_location, parameters

    @staticmethod
    def detect_content_type(filename):
        """returns content type of content (if known) for 'Content-Type' headers"""
        if filename.endswith(tuple(HTTPServer.__content_types.keys())):
            return HTTPServer.__content_types[filename.split('.')[-1]]
        else:
            return "unknown"

    @staticmethod
    def normalize_uri(uri):
        """returns uri without repeated characters"""
        repeated_chars = ['/', '?', '#']

        def replace_repeated(dupl, string):
            while dupl*2 in string:
                string = string.replace(dupl * 2, dupl)
            return string

        for duplicate in repeated_chars:
            uri = replace_repeated(duplicate, uri)

        return uri

    @staticmethod
    def decode_uri(encoded_uri):
        """returns uri with decoded characters - dictionary for translation is __encoded_chars"""
        for enc, dec in HTTPServer.__encoded_chars.iteritems():
            encoded_uri = encoded_uri.replace(enc, dec).replace(enc.lower(), dec)
        return encoded_uri

    @staticmethod
    def get_date():
        """returns value for 'Date' header"""
        return strftime("%a, %d %b %Y %H:%M:%S GMT", gmtime())

    @staticmethod
    def get_server():
        """returns value for 'Server' header"""
        return platform.system() + " " + platform.release()


def run(work):
    server = HTTPServer(address=server_addr, port=port, document_root=root, forbidden=forbidden_methods)
    server.serve_forever()

def help()
    pass

if __name__ == "__main__":
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'h:r:p:a:l:w:f', ['help=', 'root=', 'port=',
                                                                   'host=', 'log=', 'workers='
                                                                   'forbidden_methods='])
    except getopt.GetoptError:
        help()
        sys.exit(2)

    port = 8080
    server_addr = "0.0.0.0"
    workers = 10
    forbidden_methods = "POST"
    root = "/home/artem"
    log_path = None

    for opt, arg in opts:
        if opt in ('-h', '--help'):
            pass
            sys.exit(2)
        elif opt in ('-r', '--root'):
            root = arg.strip('=')
            pass
        elif opt in ('-p', '--port'):
            port = int(arg.strip('='))
            pass
        elif opt in ('-h', '--host'):
            server_addr = arg.strip('=')
            pass
        elif opt in ('-l', '--log'):
            log_path = arg.strip('=')
            pass
        elif opt in ('-w', '--workers'):
            workers = int(arg.strip('='))
            pass
        elif opt in ('-f', '--forbidden_methods'):
            forbidden_methods = arg.strip('=')
            pass
        else:
            pass

    logging.basicConfig(
        level=getattr(logging, "DEBUG"),
        format="%(process)d: %(message)s", filemode='w', filename=log_path)
    log = logging.getLogger(__name__)

    pool = multiprocessing.Pool(workers)
    p = pool.map_async(run, range(workers))

    try:
        results = p.get(0xFFFF)
    except KeyboardInterrupt:
        log.debug("parent received control-c")




