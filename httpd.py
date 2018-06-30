#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import getopt
import os
import asyncore_epoll as asyncore
import datetime
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

    def __init__(self, headers, uri="", http_version=1.1, body=None):
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

    def __init__(self, headers, uri="", http_version=1.1, body=None):
        super(HEADRequest, self).__init__(headers, uri=uri, http_version=http_version, body=body)
        self.method = "HEAD"


class POSTRequest(HTTPRequest):

    def __init__(self, headers, uri="", http_version=1.1, body=None):
        super(POSTRequest, self).__init__(headers, uri=uri, http_version=http_version, body=body)
        self.method = "POST"

    def get_params(self, query=None):
        return self.body


class HTTPServer(asyncore.dispatcher):

    index = "index"

    __CHUNK_SIZE = 8 * 10240
    __encoded_chars = {"%21": '!', "%23": '#', "%24": '$', "%26": '&', "%27": '\'',
                       "%28": '(', "%29": ')', "%2A": '*', "%2B": '+', "%2C": ',',
                       "%2F": '/', "%3A": ':', "%3B": ';', "%3D": '=', "%3F": '?',
                       "%40": '@', "%5B": '[', "%5D": ']', "+": ' '}
    __content_types = ("html", "css", "js", "jpg", "jpeg", "png", "gif", "swf")

    def __init__(self, address="", port=8080, document_root="/home/artem"):
        asyncore.dispatcher.__init__(self)
        self.address = address
        self.port = port
        self.document_root = document_root
        if self.document_root[-1:] == '/':
            self.document_root = self.document_root[:-1]

        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.bind((self.address, self.port))
        self.listen(1)
        log.debug("Listening on address %s:%s", address, port)

    def serve_forever(self):
        try:
            asyncore.loop(timeout=600, use_poll=True, poller=asyncore.epoll_poller)
        except KeyboardInterrupt:
            log.debug("Close worker")
        finally:
            self.close()

    def handle_accept(self):
        conn, addr = self.accept()
        if conn is not None and addr is not None:
            request = conn.recv(self.__CHUNK_SIZE)
            http_request = self.parse_request(request)
            self.handle_request(http_request, conn)

    def handle_request(self, http_request, connection):
        send_content = False
        os_path = None
        if not http_request:
            status_line = "HTTP/1.0 405 Method Not Allowed"
            response_headers = {
                "Host": socket.gethostname(), "Date": self.get_date(),
                "Server": self.get_server(), "Connection": "close",
            }
        else:
            os_path, parameters = self.uri_resolve(http_request)
            if os.path.isfile(os_path):
                status_line = "HTTP/1.0 200 OK"
                response_headers = {
                    "Host": socket.gethostname(), "Content-Type": self.detect_content_type(os_path),
                    "Date": self.get_date(), "Server": self.get_server(),
                    "Connection": "close", "Content-Length": os.path.getsize(os_path)
                }
                if http_request.method is not "HEAD":
                    send_content = True
            else:
                log.debug(os_path)
                status_line = "HTTP/1.0 404 Not Found"
                response_headers = {
                    "Host": socket.gethostname(), "Date": self.get_date(),
                    "Server": self.get_server(), "Connection": "close",
                }

        self.send_response(connection, status_line, **response_headers)
        if send_content:
            self.send_file(connection, os_path)

    def send_response(self, client_socket, st_line, **response_headers):
        log.debug(st_line)
        log.debug(client_socket)
        client_socket.send(st_line + "\r\n")
        for hdr, hdr_v in response_headers.items():
            client_socket.send(str(hdr) + ": " + str(hdr_v) + "\r\n")
        client_socket.send("\r\n")

    def send_file(self, client_socket, path):
        with open(path, 'rb') as f:
            data = f.read(self.__CHUNK_SIZE)
            while data:
                client_socket.send(data)
                data = f.read(self.__CHUNK_SIZE)
            f.close()

    def detect_content_type(self, filename):
        if filename.endswith(self.__content_types):
            return filename.split('.')[-1]
        else:
            return "unknown"

    def parse_request(self, request):
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
        delimiter_index = request_lines.index("")
        headers = request_lines[1:delimiter_index]
        message = "".join(request_lines[delimiter_index::])
        method, uri, http_version = parse_request_line(request_line)
        if method in http_requests:
            return http_requests[method](headers, uri, http_version, message)
        else:
            return None

    def uri_resolve(self, http_request):
        uri_parts = http_request.uri.split('?') + [None]

        if '' in uri_parts:
            uri_parts = filter(lambda a: a != '', uri_parts)

        parameters = http_request.get_params(uri_parts[1])

        resource_location = self.decode_uri(self.normalize_uri(uri_parts[0]))
        if resource_location[-1:] == '/':
            resource_location += (self.index + '.html')

        return self.document_root + resource_location, parameters

    @staticmethod
    def normalize_uri(uri):
        repeated_chars = ['/', '?', '#']

        def replace_repeated(dupl, string):
            while dupl*2 in string:
                string = string.replace(dupl * 2, dupl)
            return string

        for duplicate in repeated_chars:
            uri = replace_repeated(duplicate, uri)

        return uri

    def decode_uri(self, encoded_uri):
        for enc, dec in self.__encoded_chars.iteritems():
            encoded_uri = encoded_uri.replace(enc, dec)
        return encoded_uri

    @staticmethod
    def get_date():
        return strftime("%a, %d %b %Y %H:%M:%S GMT", gmtime())

    @staticmethod
    def get_server():
        return platform.system() + " " + platform.release()


def run():
    server = HTTPServer(address="localhost", port=8080)
    server.serve_forever()


if __name__ == "__main__":
    try:
        opts, args = getopt.getopt(sys.argv[1:], 'c:p:h:l', ['config=', 'port=', 'host=', 'log='])
    except getopt.GetoptError:
        pass
        sys.exit(2)

    for opt, arg in opts:
        if opt in ('-h', '--help'):
            pass
            sys.exit(2)
        elif opt in ('-c', '--config'):
            pass
        elif opt in ('-p', '--port'):
            pass
        elif opt in ('-h', '--host'):
            pass
        elif opt in ('-l', '--log'):
            pass
        else:
            pass

    logging.basicConfig(
        level=getattr(logging, "DEBUG"),
        format="%(name)s: %(process)d %(message)s")
    log = logging.getLogger(__name__)

    for _ in xrange(1):
        p = multiprocessing.Process(target=run)
        p.start()
