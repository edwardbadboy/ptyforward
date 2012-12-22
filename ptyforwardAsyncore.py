#!/usr/bin/python --

import sys
import os
import errno
import socket
import asyncore
from threading import Thread

_printerr = sys.stderr.write


class ForwardSession(asyncore.dispatcher_with_send):
    def __init__(self, sock, sockmap):
        asyncore.dispatcher_with_send.__init__(self, sock, sockmap)
        self._peer = None

    def linkPeer(self, peer):
        self._peer = peer

    def unlinkPeer(self):
        self._peer = None

    def sessionExit(self):
        _printerr("forward session exit %r\n" % self)
        try:
            self.close()
        except OSError as e:
            if e.errno != errno.EBADF:
                raise
        myPeer = self._peer
        self._peer = None
        if myPeer:
            myPeer.unlinkPeer()
            myPeer.sessionExit()

    def handle_read(self):
        if not self._peer:
            self.sessionExit()
            return
        data = self.recv(4096)
        if data:
            self._peer.send(data)

    def handle_close(self):
        self.sessionExit()

    def readable(self):
        if not (self._peer and self.connected):
            return False
        return len(self._peer.out_buffer) < 512


class PTYSession(ForwardSession, asyncore.file_dispatcher):
    def __init__(self, pty, sockmap):
        ForwardSession.__init__(self, None, sockmap)
        asyncore.file_dispatcher.__init__(self, pty, sockmap)


def _safeShutdown(client, how):
    try:
        client.shutdown(how)
    except:
        pass


def _readLine(sock):
    l = []
    while True:
        c = sock.recv(1)
        if len(c) == 0:
            break
        l.append(c)
        if c == '\n':
            break
    return ''.join(l).rstrip('\r\n')


def _serveRequest(client, addr):
    _printerr('client connected: %r\n' % (addr, ))
    ptydev = _readLine(client)
    _printerr('pty dev: %s\n' % ptydev)

    pty = None
    try:
        pty = os.open(ptydev, os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY)
    except (IOError, OSError) as e:
        client.send("Error open PTY dev %s: %r\n" % (ptydev, e))
        client.shutdown(socket.SHUT_RDWR)
        client.close()
        if pty:
            os.close(pty)
        return

    sockMap = {}
    sockSession = ForwardSession(client, sockMap)
    ptySession = PTYSession(pty, sockMap)
    os.close(pty)
    sockSession.linkPeer(ptySession)
    ptySession.linkPeer(sockSession)

    asyncore.loop(use_poll=True, map=sockMap)


def _serve(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', port))
    s.listen(1)
    while True:
        client, addr = s.accept()
        servant = Thread(target=_serveRequest, args=(client, addr))
        servant.daemon = True
        servant.start()
    s.close()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        _printerr('Usage: %s port\n' % sys.argv[0])
        sys.exit(1)

    t = Thread(target=_serve, args=(int(sys.argv[1]),))
    t.start()
    t.join()
