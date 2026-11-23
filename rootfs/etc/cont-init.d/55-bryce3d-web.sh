#!/bin/sh
# Browser-side tweaks for the web UI.
set -u
CSS=/opt/noVNC/app/styles/base.css
MARK="/* bryce3d: sharp scaling */"
if [ "${SHARP_SCALING:-1}" = "1" ]; then
    if ! grep -qF "$MARK" "$CSS"; then
        printf '\n%s\n#noVNC_container canvas { image-rendering: pixelated; image-rendering: crisp-edges; }\n' "$MARK" >> "$CSS"
    fi
else
    # Remove the rule if it was added on an earlier start.
    sed -i "\|$MARK|,+1d" "$CSS"
fi
