# Bryce 3D (1997, MetaCreations) running under Wine, served to your browser via noVNC.
FROM jlesage/baseimage-gui:debian-12-v4

# Wine with 32-bit support (needed for the 16-bit SETUP.EXE on the Bryce CD),
# plus tools to unpack the CD image / zip.
RUN dpkg --add-architecture i386 && \
    add-pkg \
        wine wine32 wine64 \
        p7zip-full unzip genisoimage \
        x11-utils fonts-liberation procps xdotool python3

COPY rootfs/ /

# - Xvnc moves to /tmp/vnc-x.sock; the click-fix proxy takes over /tmp/vnc.sock
#   (where the web UI connects) and relays to it.
# - /etc/openbox/main-window-selection.xml: the base image maximizes,
#   undecorates and buries every window matching it (by default every normal
#   window). Bryce's palettes and dialogs are separate windows, so we make it
#   match nothing.
# - Xvnc refuses screen-resize requests from the browser (noVNC defaults to
#   "remote resizing", which would stretch the screen to the browser window;
#   Bryce needs a fixed screen). ALLOW_REMOTE_RESIZE=1 turns that back on.
RUN sed -i 's#-rfbunixpath=/tmp/vnc.sock#-rfbunixpath=/tmp/vnc-x.sock#' /etc/services.d/xvnc/params && \
    grep -q vnc-x.sock /etc/services.d/xvnc/params && \
    sed -i 's|^# Desktop (app) name.|[ "${ALLOW_REMOTE_RESIZE:-0}" = "1" ] \|\| echo "-AcceptSetDesktopSize=0"\n&|' /etc/services.d/xvnc/params && \
    grep -q AcceptSetDesktopSize=0 /etc/services.d/xvnc/params && \
    ln -sf /defaults/service/sgid /etc/services.d/clickproxy/sgid && \
    chmod +x /startapp.sh && \
    set-cont-env APP_NAME "Bryce 3D" && \
    set-cont-env APP_VERSION "3.0"

ENV KEEP_APP_RUNNING=1 \
    DISPLAY_WIDTH=1024 \
    DISPLAY_HEIGHT=768 \
    WINEDEBUG=-all

# /config  -> Wine prefix + installed Bryce (Unraid appdata)
# /storage -> your share: put the Bryce ISO (or a zip containing it) here.
#             Also shows up inside Windows as drive E: for scenes/renders.
VOLUME ["/config", "/storage"]

EXPOSE 5800 5900
