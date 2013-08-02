/*
 * WebSockets telnet client
 * Copyright (C) 2011 Joel Martin
 * Licensed under LGPL-3 (see LICENSE.txt)
 *
 * Includes VT100.js from:
 *   http://code.google.com/p/sshconsole
 * Which was modified from:
 *   http://fzort.org/bi/o.php#vt100_js
 *
 * ANSI escape sequeneces:
 *   http://en.wikipedia.org/wiki/ANSI_escape_code
 *   http://ascii-table.com/ansi-escape-sequences-vt-100.php
 *   http://www.termsys.demon.co.uk/vtansi.htm
 *   http://invisible-island.net/xterm/ctlseqs/ctlseqs.html
 *
 * ASCII codes:
 *   http://en.wikipedia.org/wiki/ASCII
 *   http://www.hobbyprojects.com/ascii-table/ascii-table.html
 *
 * Other web consoles:
 *   http://stackoverflow.com/questions/244750/ajax-console-window-with-ansi-vt100-support
 */




function WSPTY(target, connect_callback, disconnect_callback) {

var that = {},  // Public API interface
    vt100, ws, sQ = [];
    termType = "VT100";


Array.prototype.pushStr = function (str) {
    var n = str.length;
    for (var i=0; i < n; i++) {
        this.push(str.charCodeAt(i));
    }
}

function do_send() {
    if (sQ.length > 0) {
        Util.Debug("Sending " + sQ);
        ws.send(sQ);
        sQ = [];
    }
}

function do_recv() {
    //console.log(">> do_recv");
    var arr = ws.rQshiftBytes(ws.rQlen()), str = "",
        chr, cmd, code, value;

    Util.Debug("Received array '" + arr + "'");
    while (arr.length > 0) {
        chr = arr.shift();
        str += String.fromCharCode(chr);
    }

    if (sQ) {
        do_send();
    }

    if (str) {
        vt100.write(str);
    }

    //console.log("<< do_recv");
}



that.connect = function(host, port, ptydev, encrypt) {
    var host = host,
        port = port,
        ptydev = ptydev,
        scheme = "ws://", uri;

    Util.Debug(">> connect");
    if ((!host) || (!port)) {
        console.log("must set host and port");
        return;
    }

    if (ws) {
        ws.close();
    }

    if (encrypt) {
        scheme = "wss://";
    }
    uri = scheme + host + ":" + port + "/ws?pty=" + encodeURIComponent(ptydev);
    Util.Info("connecting to " + uri);

    ws.open(uri);

    Util.Debug("<< connect");
}

that.disconnect = function() {
    Util.Debug(">> disconnect");
    if (ws) {
        ws.close();
    }
    vt100.curs_set(true, false);

    disconnect_callback();
    Util.Debug("<< disconnect");
}


function constructor() {
    /* Initialize Websock object */
    ws = new Websock();

    ws.on('message', do_recv);
    ws.on('open', function(e) {
        Util.Info(">> WebSockets.onopen");
        vt100.curs_set(true, true);
        connect_callback();
        Util.Info("<< WebSockets.onopen");
    });
    ws.on('close', function(e) {
        Util.Info(">> WebSockets.onclose");
        that.disconnect();
        Util.Info("<< WebSockets.onclose");
    });
    ws.on('error', function(e) {
        Util.Info(">> WebSockets.onerror");
        that.disconnect();
        Util.Info("<< WebSockets.onerror");
    });

    /* Initialize the terminal emulator/renderer */

    vt100 = new VT100(80, 24, target);
    vt100.noecho();


    /*
     * Override VT100 I/O routines
     */

    // Set handler for sending characters
    vt100.getch(
        function send_chr(chr, vt) {
            var i;
            Util.Debug(">> send_chr: " + chr);
            for (i = 0; i < chr.length; i++) {
                sQ.push(chr.charCodeAt(i));
            }
            do_send();
            vt100.getch(send_chr);
        }
    );

    vt100.debug = function(message) {
        Util.Debug(message + "\n");
    }

    vt100.warn = function(message) {
        Util.Warn(message + "\n");
    }

    vt100.curs_set = function(vis, grab, eventist)
    {
        this.debug("curs_set:: vis: " + vis + ", grab: " + grab);
        if (vis !== undefined)
            this.cursor_vis_ = (vis > 0);
        if (eventist === undefined)
            eventist = window;
        if (grab === true || grab === false) {
            if (grab === this.grab_events_)
                return;
            if (grab) {
                this.grab_events_ = true;
                VT100.the_vt_ = this;
                Util.addEvent(eventist, 'keydown', vt100.key_down);
                Util.addEvent(eventist, 'keyup', vt100.key_up);
            } else {
                Util.removeEvent(eventist, 'keydown', vt100.key_down);
                Util.removeEvent(eventist, 'keyup', vt100.key_up);
                this.grab_events_ = false;
                VT100.the_vt_ = undefined;
            }
        }
    }

    vt100.key_down = function(e) {
        var vt = VT100.the_vt_, keysym, ch, str = "";

        if (vt === undefined)
            return true;

        keysym = getKeysym(e);
		Util.Error("Got keysym " + keysym);

        if (keysym < 128) {
            if (e.ctrlKey) {
                if (keysym == 64) {
                    // control 0
                    ch = 0;
                } else if ((keysym >= 97) && (keysym <= 122)) {
                    // control codes 1-26
                    ch = keysym - 96;
                } else if ((keysym >= 91) && (keysym <= 95)) {
                    // control codes 27-31
                    ch = keysym - 64;
                } else {
                    Util.Info("Debug unknown control keysym: " + keysym);
                }
            } else {
                ch = keysym;
            }
            str = String.fromCharCode(ch);
        } else {
            switch (keysym) {
            case 65505: // Shift, do not send directly
                break;
            case 65507: // Ctrl, do not send directly
                break;
            case 65293: // Carriage return, line feed
                str = '\n'; break;
            case 65288: // Backspace
                str = '\b'; break;
            case 65289: // Tab
                str = '\t'; break;
            case 65307: // Escape
                str = '\x1b'; break;
            case 65361: // Left arrow 
                str = '\x1b[D'; break;
            case 65362: // Up arrow 
                str = '\x1b[A'; break;
            case 65363: // Right arrow 
                str = '\x1b[C'; break;
            case 65364: // Down arrow 
                str = '\x1b[B'; break;
            case 173: // minus sign
                if (e.shiftKey) {
                    str = '_';
                } else {
                    str = '-';
                }
                break;
            default:
                Util.Error("Unrecoginized keysym " + keysym);
            }
        }

        if (str) {
            vt.key_buf_.push(str);
            setTimeout(VT100.go_getch_, 0);
        }

        Util.stopEvent(e);
        return false;
    }

    vt100.key_up = function(e) {
        var vt = VT100.the_vt_;
        if (vt === undefined)
            return true;
        Util.stopEvent(e);
        return false;
    }


    return that;
}

return constructor(); // Return the public API interface

} // End of wspty()
