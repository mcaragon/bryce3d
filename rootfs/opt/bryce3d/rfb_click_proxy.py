#!/usr/bin/env python3
"""VNC (RFB) proxy between the web UI and Xvnc that fixes Bryce's preset pop-ups.

Bryce 3D opens its preset libraries (the small arrows next to Create, Edit and
Sky & Fog on the top palette) on mouse-DOWN, and closes them if the button is
released while the pop-up is open but not over an item. That was fine in 1997,
when the pop-up took longer to appear than a click. Today it appears within a
few milliseconds, so a normal click opens it and closes it again at once.

When button 1 goes down on one of those arrows, this proxy forwards the press,
sends a release a few milliseconds later, and drops the user's real release.
All other input passes through unchanged. Messages from the server are never
inspected. If the client sends anything this proxy does not understand, it
stops interpreting and just relays bytes, so it can never break the session.

Credit: the idea and the arrow positions come from the BryceDock project
(https://github.com/RaymonDev/BryceDock). This is an independent implementation.
"""
import argparse
import asyncio
import os
import struct
import subprocess
import sys
import time

PALETTE_SIZE = (500, 80)           # Bryce's top palette window
ARROWS = [(52, 82), (114, 144), (217, 247)]   # x ranges inside it, y in 0..26
ARROW_Y = (0, 26)
QUICK_RELEASE = 0.008
ENABLED = os.environ.get("CLICK_FIX", "1") != "0"


def log(*a):
    print("[clickproxy]", *a, file=sys.stderr, flush=True)


class Palette:
    """Finds where Bryce's top palette window is on screen (polled with xdotool)."""

    def __init__(self):
        self.origin = None
        self.checked = 0.0

    def refresh(self):
        if time.monotonic() - self.checked < 1.0:
            return
        self.checked = time.monotonic()
        try:
            out = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--name", ".",
                 "getwindowgeometry", "--shell", "%@"],
                capture_output=True, text=True, timeout=2,
                env={**os.environ, "DISPLAY": os.environ.get("DISPLAY", ":0")},
            ).stdout
        except Exception:
            return
        self.origin = None
        cur = {}
        for line in out.splitlines():
            k, _, v = line.partition("=")
            cur[k] = v
            if k == "SCREEN":
                try:
                    if (int(cur["WIDTH"]), int(cur["HEIGHT"])) == PALETTE_SIZE:
                        self.origin = (int(cur["X"]), int(cur["Y"]))
                        return
                except (KeyError, ValueError):
                    pass
                cur = {}

    def on_arrow(self, x, y):
        self.refresh()
        if self.origin is None:
            return False
        rx, ry = x - self.origin[0], y - self.origin[1]
        return ARROW_Y[0] <= ry <= ARROW_Y[1] and any(a <= rx <= b for a, b in ARROWS)


async def exactly(reader, n):
    return await reader.readexactly(n) if n else b""


async def pipe_raw(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()


async def client_to_server(reader, writer, palette):
    """Relay client->server, interpreting messages so pointer events can be adjusted."""
    send = writer.write
    try:
        version = await exactly(reader, 12)
        send(version)
        if not version.startswith(b"RFB 003.003"):
            sec = await exactly(reader, 1)       # chosen security type
            send(sec)
            if sec[0] == 2:                       # VNC password: 16-byte response
                send(await exactly(reader, 16))
            elif sec[0] != 1:                     # anything fancier: just relay
                return await pipe_raw(reader, writer)
        send(await exactly(reader, 1))            # ClientInit

        swallow = False   # True while the user's button is held after a fixed click
        while True:
            t = (await exactly(reader, 1))[0]
            if t == 5:                            # PointerEvent
                body = await exactly(reader, 5)
                mask, x, y = body[0], *struct.unpack(">HH", body[1:])
                if swallow:
                    if not mask & 1:
                        swallow = False
                    mask &= ~1                    # hide the held button from Bryce
                    send(bytes([5, mask]) + body[1:])
                elif ENABLED and mask & 1 and palette.on_arrow(x, y):
                    send(bytes([5]) + body)                       # press
                    await writer.drain()
                    await asyncio.sleep(QUICK_RELEASE)
                    send(bytes([5, mask & ~1]) + body[1:])        # early release
                    swallow = True
                else:
                    send(bytes([5]) + body)
            elif t == 0:   send(bytes([t]) + await exactly(reader, 19))   # SetPixelFormat
            elif t == 2:                                                 # SetEncodings
                head = await exactly(reader, 3)
                n = struct.unpack(">H", head[1:])[0]
                send(bytes([t]) + head + await exactly(reader, 4 * n))
            elif t == 3:   send(bytes([t]) + await exactly(reader, 9))    # FB update request
            elif t == 4:   send(bytes([t]) + await exactly(reader, 7))    # KeyEvent
            elif t == 6:                                                 # ClientCutText
                head = await exactly(reader, 7)
                n = struct.unpack(">i", head[3:])[0]
                send(bytes([t]) + head + await exactly(reader, abs(n)))
            elif t == 150: send(bytes([t]) + await exactly(reader, 9))    # Continuous updates
            elif t == 248:                                               # Fence
                head = await exactly(reader, 8)
                send(bytes([t]) + head + await exactly(reader, head[7]))
            elif t == 250: send(bytes([t]) + await exactly(reader, 3))    # xvp
            elif t == 251:                                               # SetDesktopSize
                head = await exactly(reader, 7)
                send(bytes([t]) + head + await exactly(reader, 16 * head[5]))
            elif t == 255:                                               # QEMU messages
                sub = await exactly(reader, 1)
                if sub[0] == 0:                                          # extended key event
                    send(bytes([t]) + sub + await exactly(reader, 10))
                else:
                    send(bytes([t]) + sub)
                    return await pipe_raw(reader, writer)
            else:                                 # unknown: stop interpreting
                send(bytes([t]))
                return await pipe_raw(reader, writer)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()


async def handle(c_reader, c_writer, target, palette):
    try:
        s_reader, s_writer = await asyncio.open_unix_connection(target)
    except OSError as e:
        log("cannot reach Xvnc:", e)
        c_writer.close()
        return
    await asyncio.gather(
        client_to_server(c_reader, s_writer, palette),
        pipe_raw(s_reader, c_writer),
    )


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", required=True)
    ap.add_argument("--target", required=True)
    args = ap.parse_args()
    palette = Palette()
    try:
        os.unlink(args.listen)
    except FileNotFoundError:
        pass
    server = await asyncio.start_unix_server(
        lambda r, w: handle(r, w, args.target, palette), path=args.listen)
    os.chmod(args.listen, 0o660)
    log(f"listening on {args.listen} -> {args.target} (click fix {'on' if ENABLED else 'off'})")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
