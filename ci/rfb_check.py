#!/usr/bin/env python3
"""CI check run inside the container: does a VNC client get through the click-fix
proxy (/tmp/vnc.sock) to Xvnc and receive the screen size?"""
import socket, struct, sys
s = socket.socket(socket.AF_UNIX); s.settimeout(10); s.connect("/tmp/vnc.sock")
def rx(n):
    b = b""
    while len(b) < n:
        c = s.recv(n - len(b))
        if not c: sys.exit("connection closed")
        b += c
    return b
ver = rx(12); s.sendall(b"RFB 003.008\n")
types = rx(rx(1)[0])
assert 1 in types, f"no 'None' security type offered: {list(types)}"
s.sendall(b"\x01"); assert struct.unpack(">I", rx(4))[0] == 0, "security failed"
s.sendall(b"\x01")                                  # ClientInit (shared)
w, h = struct.unpack(">HH", rx(4)); rx(16); name = rx(struct.unpack(">I", rx(4))[0])
s.sendall(bytes([5, 0]) + struct.pack(">HH", 10, 10))   # a pointer event through the proxy
print(f"OK: {ver.strip().decode()} via proxy, screen {w}x{h}, desktop {name.decode()!r}")
