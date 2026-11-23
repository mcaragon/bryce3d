#!/bin/sh
# Launches Bryce 3D. On first start it locates the CD image in /storage,
# unpacks it, mounts it as Windows drive D: (CD-ROM) and runs the installer.
set -u

export HOME=/config
export WINEPREFIX=/config/wine
export WINEARCH=win32
export WINEDEBUG="${WINEDEBUG:--all}"
export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-mscoree,mshtml=}"

STORAGE=/storage
CD=/config/cdrom
DESKTOP="Bryce,${DISPLAY_WIDTH:-1280}x${DISPLAY_HEIGHT:-960}"

log() { echo "[bryce3d] $*"; }
fail() {
    log "ERROR: $*"
    xmessage -center -buttons Retry:0 "Bryce 3D container: $*" >/dev/null 2>&1
    exit 1   # app is restarted automatically (KEEP_APP_RUNNING=1)
}

WINESERVER="$(command -v wineserver || ls /usr/lib/wine/wineserver* 2>/dev/null | head -1)"
wsw() { "$WINESERVER" -w; }

# Linux path -> Windows path for the two drives we care about (C: and D:)
winpath() {
    case "$1" in
        "$CD"/*)                  rel="${1#"$CD"/}"; drv="D:" ;;
        "$WINEPREFIX/drive_c"/*)  rel="${1#"$WINEPREFIX/drive_c"/}"; drv="C:" ;;
        *) echo "$1"; return ;;
    esac
    printf '%s\\%s\n' "$drv" "$(printf '%s' "$rel" | tr '/' '\\')"
}

find_setup() { find "$1" -maxdepth 2 -iname 'setup.exe' 2>/dev/null | awk '{print length, $0}' | sort -n | head -1 | cut -d' ' -f2-; }

# ---------------------------------------------------------------- CD image
prepare_cd() {
    [ -f "$CD/.ready" ] && return 0
    rm -rf "$CD" && mkdir -p "$CD"

    iso="$(find "$STORAGE" -maxdepth 3 -iname '*.iso' 2>/dev/null | head -1)"
    if [ -z "$iso" ]; then
        zip="$(find "$STORAGE" -maxdepth 2 -iname '*.zip' 2>/dev/null | head -1)"
        if [ -n "$zip" ]; then
            log "Unzipping $zip ..."
            rm -rf /config/unzipped && mkdir -p /config/unzipped
            unzip -q -o "$zip" -d /config/unzipped || fail "could not unzip $zip"
            iso="$(find /config/unzipped -iname '*.iso' | head -1)"
        fi
    fi

    if [ -n "$iso" ]; then
        log "Extracting CD image $iso ..."
        7z x -y -o"$CD" "$iso" >/dev/null || fail "could not extract $iso"
        label="$(isoinfo -d -i "$iso" 2>/dev/null | sed -n 's/^Volume id: *//p')"
        [ -n "$label" ] && printf '%s' "$label" > "$CD/.windows-label"
    else
        # Maybe the CD contents were copied as plain files.
        src="$(find_setup "$STORAGE")"
        [ -z "$src" ] && [ -d /config/unzipped ] && src="$(find_setup /config/unzipped)"
        [ -z "$src" ] && fail "no Bryce .iso, .zip or SETUP.EXE found in the storage share. Copy it there and press Retry."
        log "Copying CD files from $(dirname "$src") ..."
        cp -a "$(dirname "$src")/." "$CD/"
    fi
    rm -rf /config/unzipped
    [ -n "$(find_setup "$CD")" ] || fail "the CD image does not contain SETUP.EXE"
    touch "$CD/.ready"
}

# ---------------------------------------------------------------- Wine prefix
prepare_wine() {
    if [ ! -f "$WINEPREFIX/system.reg" ]; then
        log "Creating Wine prefix (first run, takes a minute) ..."
        # WINEDLLOVERRIDES (set above) stops Wine popping up a blocking dialog
        # offering to download Mono/Gecko, which Bryce doesn't need.
        WINEDEBUG=err+all,fixme-all timeout 300 wine wineboot -i >/config/wineboot.log 2>&1
        log "wineboot exited with status $? (output below)"
        tail -20 /config/wineboot.log
        # Leftover helper processes (explorer, services) can keep wineserver
        # alive; give them a minute, then shut it down cleanly.
        timeout 60 "$WINESERVER" -w || "$WINESERVER" -k
        log "Wine prefix ready."
        # Windows 95-era app: report Windows 98.
        wine reg add 'HKCU\Software\Wine' /v Version /d win98 /f >/dev/null 2>&1
    fi
    # D: = Bryce CD (as a real CD-ROM drive), E: = storage share
    rm -f "$WINEPREFIX/dosdevices/d:" "$WINEPREFIX/dosdevices/d::" \
          "$WINEPREFIX/dosdevices/e:" "$WINEPREFIX/dosdevices/e::"
    ln -s "$CD" "$WINEPREFIX/dosdevices/d:"
    ln -s "$STORAGE" "$WINEPREFIX/dosdevices/e:"
    wine reg add 'HKLM\Software\Wine\Drives' /v 'd:' /d cdrom /f >/dev/null 2>&1
    wine reg add 'HKLM\Software\Wine\Drives' /v 'e:' /d hd /f >/dev/null 2>&1
    # Hand keyboard focus to windows the simple way; Wine's default
    # (WM_TAKE_FOCUS) can leave dialogs unable to receive input.
    wine reg add 'HKCU\Software\Wine\X11 Driver' /v UseTakeFocus /d N /f >/dev/null 2>&1
    wsw
}

find_bryce() {
    if [ -n "${BRYCE_EXE:-}" ]; then echo "$BRYCE_EXE"; return; fi
    find "$WINEPREFIX/drive_c" -iname 'bryce*.exe' ! -iname '*unins*' ! -iname '*setup*' 2>/dev/null | head -1
}

prepare_cd
prepare_wine

exe="$(find_bryce)"
if [ -z "$exe" ]; then
    setup="$(find_setup "$CD")"
    log "Bryce not installed yet, running installer $setup"
    cd "$(dirname "$setup")"
    # No Wine virtual desktop for the installer: inside one, the InstallShield
    # full-screen billboard stays on top and hides the "Welcome" dialog.
    # As plain X windows, the window manager raises each new dialog.
    if [ "${INSTALLER_DESKTOP:-0}" = "1" ]; then
        wine explorer /desktop="$DESKTOP" "$(winpath "$setup")"
    else
        wine "$(winpath "$setup")"
    fi
    wsw
    exe="$(find_bryce)"
    [ -z "$exe" ] && fail "installer finished but no Bryce executable was found. Press Retry to run the installer again."
fi

log "Starting $exe"
cd "$(dirname "$exe")"
# Run Bryce as a plain window (like on a real PC), not inside a Wine virtual
# desktop. BRYCE_DESKTOP=1 restores the virtual-desktop behaviour.
if [ "${BRYCE_DESKTOP:-0}" = "1" ]; then
    wine explorer /desktop="$DESKTOP" "$(winpath "$exe")"
else
    wine "$(winpath "$exe")"
fi
wsw
