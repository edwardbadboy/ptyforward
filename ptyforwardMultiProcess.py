#!/usr/bin/python --

import sys
import os
import errno
import time

from multiprocessing import Process
import socket as gsocket

_printerr = sys.stderr.write

LAGTIME = 0.010  # second


def _safeShutdown(client, how):
    try:
        client.shutdown(how)
    except:
        pass


def _writeAll(writefun, to, data):
    while data:
        try:
            if to is None:
                count = writefun(data)
            else:
                count = writefun(to, data)
            if count == 0:
                return False
            data = data[count:]
        except OSError as e:
            if e.errno not in (errno.EAGAIN, errno.EINTR):
                raise
    return True


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


def _joinAny(processes):
    toWait = True
    while toWait:
        for t in processes:
            t.join(1)
            if not t.is_alive():
                _printerr('ready %r\n' % t)
                toWait = False
    for t in processes:
        if t.is_alive():
            t.join(1)
        if t.is_alive():
            _printerr('killing %r\n' % t)
            t.terminate()
            _printerr('killed %r\n' % t)


def _forwardPtyRead(pty, client, addr):
    _printerr('forwardPryRead enter\n')
    try:
        lastTime = time.time()
        while True:
            data = os.read(pty, 4096)
            if len(data) == 0:
                break
            if not _writeAll(client.send, None, data):
                break
            thisTime = time.time()
            delta = thisTime - lastTime
            lastTime = thisTime
            if delta < LAGTIME:
                time.sleep(LAGTIME - delta)
    finally:
        _safeShutdown(client, gsocket.SHUT_WR)
        _printerr('forwardPryRead exit %r\n' % (addr, ))


def _forwardPtyWrite(pty, client, addr):
    _printerr('forwardPryWrite enter\n')
    try:
        lastTime = time.time()
        while True:
            data = client.recv(4096)
            if len(data) == 0:
                break
            if not _writeAll(os.write, pty, data):
                break
            thisTime = time.time()
            delta = thisTime - lastTime
            lastTime = thisTime
            if delta < LAGTIME:
                time.sleep(LAGTIME - delta)
    finally:
        _printerr('forwardPryWrite exit %r\n' % (addr, ))


def _serveRequest(client, addr):
    _printerr('client connected: %r\n' % (addr, ))
    ptydev = _readLine(client)
    _printerr('pty dev: %s\n' % ptydev)

    pty = None

    def _clean():
        _safeShutdown(client, gsocket.SHUT_RDWR)
        client.close()
        if pty:
            os.close(pty)

    try:
        pty = os.open(ptydev, os.O_RDWR | os.O_NOCTTY)
    except (IOError, OSError) as e:
        client.send("Error open PTY dev %s: %r\n" % (ptydev, e))
        _clean()
        return

    r = Process(target=_forwardPtyRead, args=(pty, client, addr))
    w = Process(target=_forwardPtyWrite, args=(pty, client, addr))
    r.start()
    w.start()
    _joinAny([r, w])
    _clean()


def _serve(port):
    s = gsocket.socket(gsocket.AF_INET, gsocket.SOCK_STREAM)
    s.setsockopt(gsocket.SOL_SOCKET, gsocket.SO_REUSEADDR, 1)
    s.bind(('0.0.0.0', port))
    s.listen(1)
    while True:
        client, addr = s.accept()
        servant = Process(target=_serveRequest, args=(client, addr))
        servant.start()
        servant.join()
    s.close()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        _printerr('Usage: %s port\n' % sys.argv[0])
        sys.exit(1)

    t = Process(target=_serve, args=(int(sys.argv[1]),))
    t.start()
    t.join()
