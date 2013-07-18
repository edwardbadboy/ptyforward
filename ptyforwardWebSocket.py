#!/usr/bin/python --

import gevent.monkey
gevent.monkey.patch_all()
import gevent
import gevent.socket as gsocket

import sys
import os
import errno
import time
import wsgiref.util as wsutil
import urllib
import urlparse

from ws4py.websocket import WebSocket
from ws4py.server.geventserver import WSGIServer
from ws4py.server.wsgiutils import WebSocketWSGIApplication


_printerr = sys.stderr.write

LAGTIME = 0.010  # second


def _writeAll(writefun, to, data):
    while data:
        try:
            if to is None:
                count = writefun(data)
            else:
                gsocket.wait_write(to)
                count = writefun(to, data)
            if count == 0:
                return False
            data = data[count:]
        except OSError as e:
            if e.errno not in (errno.EAGAIN, errno.EINTR):
                raise
    return True


class PtyWebSocket(WebSocket):
    def __init__(self, *args, **kwargs):
        self.ptyPath = None
        self.pty = None
        self.sendPtyDataThread = None
        super(PtyWebSocket, self).__init__(*args, **kwargs)

    def _request_uri(self):
        return wsutil.request_uri(self.environ, include_query=1)

    def _sendPtyDataProc(self):
        try:
            lastTime = time.time()
            while True:
                gsocket.wait_read(self.pty)
                data = os.read(self.pty, 4096)
                if len(data) == 0:
                    break
                self.send(data, binary=True)
                thisTime = time.time()
                delta = thisTime - lastTime
                if delta < LAGTIME:
                    gevent.sleep(LAGTIME - delta)
        finally:
            self.close(reason="Done reading pty data %s" % self.ptyPath)

    def opened(self):
        _base, query = urllib.splitquery(self._request_uri())
        qdict = urlparse.parse_qs(query)
        try:
            self.ptyPath = qdict['pty'][0]
            self.pty = os.open(self.ptyPath,
                               os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY)
            self.sendPtyDataThread = gevent.spawn(self._sendPtyDataProc)
            _printerr("Done handshake pty: %s %s\n" % (self.ptyPath, self.pty))
        except Exception as e:
            _printerr("open pty error:\n%s\n" % e)
            self.close(reason='Error open pty:\n%s' % e)

    def closed(self, code, reason=None):
        _printerr("WebSocket closed: code %s reason %s\n" % (code, reason))
        if self.sendPtyDataThread:
            gevent.kill(self.sendPtyDataThread)
        if self.pty:
            try:
                os.close(self.pty)
                self.pty = None
            except Exception as e:
                _printerr("Failed to close pty:\n%s\n" % e)

    def received_message(self, message):
        if not message.is_binary:
            return
        self.lastRecvMsgTime = time.time()
        if not _writeAll(os.write, self.pty, message.data):
            self.close(reason='Error write pty:\n%s' % self.pty)
        thisTime = time.time()
        delta = thisTime - self.lastRecvMsgTime
        self.lastRecvMsgTime = thisTime
        if delta < LAGTIME:
            gevent.sleep(LAGTIME - delta)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        _printerr('Usage: %s port\n' % sys.argv[0])
        sys.exit(1)

    server = WSGIServer(('0.0.0.0', int(sys.argv[1])),
                        WebSocketWSGIApplication(handler_cls=PtyWebSocket))
    server.serve_forever()
