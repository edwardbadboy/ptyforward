#!/usr/bin/bash --

if [ -z "$1" ]; then
	exit 1
fi

if [ "$2" != "post" ]; then
(socat tcp:127.0.0.1:8888,nodelay exec:"\\\"$0\\\" \\\"$1\\\" post",fdin=5,fdout=6)
r=$?
reset
exit $r
fi

echo -e "$1\n" >&6

socat fd:5'!!'fd:6 -,raw,echo=0,escape=0x1d,cr0
