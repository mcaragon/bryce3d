# Bryce 3D (1997, MetaCreations) running under Wine, served to your browser via noVNC.
FROM jlesage/baseimage-gui:debian-12-v4

# Wine with 32-bit support (needed for the 16-bit SETUP.EXE on the Bryce CD),
# plus tools to unpack the CD image / zip.
RUN dpkg --add-architecture i386 && \
    add-pkg \
        wine wine32 wine64 \
        p7zip-full unzip genisoimage \
        x11-utils fonts-liberation procps xdotool

COPY rootfs/ /

RUN chmod +x /startapp.sh && \
    set-cont-env APP_NAME "Bryce 3D" && \
    set-cont-env APP_VERSION "3.0"

ENV KEEP_APP_RUNNING=1 \
    DISPLAY_WIDTH=640 \
    DISPLAY_HEIGHT=480 \
    WINEDEBUG=-all

# /config  -> Wine prefix + installed Bryce (Unraid appdata)
# /storage -> your share: put the Bryce ISO (or a zip containing it) here.
#             Also shows up inside Windows as drive E: for scenes/renders.
VOLUME ["/config", "/storage"]

EXPOSE 5800 5900
