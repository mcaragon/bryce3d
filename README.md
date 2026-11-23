# bryce3d

Bryce 3D (MetaCreations, 1997) in a Docker container for Unraid, used from any browser.

The Windows version of Bryce runs under Wine inside the container. The screen is served over noVNC (built on [jlesage/baseimage-gui](https://github.com/jlesage/docker-baseimage-gui)), so you open `http://UNRAID-IP:5800` on your laptop and use Bryce in the browser tab.

## How it works

| Container path | Unraid path (default) | Purpose |
|---|---|---|
| `/storage` | `/mnt/user/bryce3d` (new share) | Put the Bryce CD `.iso` here, or the `.zip` holding it. Inside Bryce this share is drive **E:**, so save scenes and renders there to get them on your network. |
| `/config` | `/mnt/user/appdata/bryce3d` | Wine prefix, the installed Bryce, and the unpacked CD |

On first start the container:
1. Finds the `.iso` in `/storage`. It also accepts a `.zip` with the ISO inside, or the CD files copied loose.
2. Unpacks the ISO and mounts it in Wine as CD-ROM drive **D:** with the original volume label.
3. Runs the Bryce `SETUP.EXE` (16-bit, handled by 32-bit Wine).
4. After that, starts Bryce directly every time.

If Bryce is closed, it opens again on its own.

## Setup on Unraid

1. **Create the share.** Go to *Shares → Add Share*, name it `bryce3d`, and copy your Bryce ISO or zip into it from your laptop (SMB: `\\UNRAID\bryce3d`).
2. **Get the image.** GitHub Actions builds it and publishes it to `ghcr.io/mcaragon/bryce3d:latest` on every push to `main`. If the repository is private, either make the package public (GitHub → your profile → *Packages* → `bryce3d` → *Package settings* → *Change visibility*), or build on the server instead (see below).
3. **Add the container.** Copy the template onto the flash drive, from the Unraid terminal:
   ```bash
   wget -O /boot/config/plugins/dockerMan/templates-user/my-bryce3d.xml https://raw.githubusercontent.com/mcaragon/bryce3d/main/unraid/bryce3d.xml
   ```
   Then go to *Docker → Add Container → Template: bryce3d → Apply*. (A private repo needs the file copied manually instead.)

   The template sets **Extra Parameters** to `--security-opt seccomp=unconfined`. Keep it. Docker's default system-call filter blocks something 32-bit Wine needs, and without it startup hangs at "Creating Wine prefix" with `wine: socket : Function not implemented` in the log. This setting turns off that filter for this one container only.
4. **Install Bryce.** Open the WebUI (`http://UNRAID-IP:5800`). The installer appears after a minute or two on first run. Accept the defaults, and **type** the serial number by hand, because pasting doesn't work in that dialog. The serial is in the text file on the CD or zip, or on the archive.org item page.

### Building locally instead of pulling

```bash
git clone https://github.com/mcaragon/bryce3d.git /mnt/user/appdata/bryce3d-src
```
```bash
cd /mnt/user/appdata/bryce3d-src && docker build -t bryce3d .
```
Then set *Repository* in the template to `bryce3d`.

## Tips

- **Screen size.** Change `DISPLAY_WIDTH` / `DISPLAY_HEIGHT` in the template. Wine runs Bryce in a virtual desktop of exactly that size.
- **Bryce render resolution.** Use *File → Document Setup*, then save a scene named `DEFAULT` in the Bryce folder so it opens at that size every time.
- **Clipboard / file transfer.** Open the noVNC side panel (the arrow on the left edge). Exchanging files through the share (drive E:) is the easiest route.
- **Password.** The UI has no login by default. Keep it on your LAN, or set `WEB_AUTHENTICATION=1` with a username and password. That also needs `SECURE_CONNECTION=1` (HTTPS) or `WEB_AUTHENTICATION_ALLOW_INSECURE=1`.
- **Reinstall from scratch.** Stop the container and delete `/mnt/user/appdata/bryce3d/wine`. To use a different ISO, also delete `.../cdrom`.
- **Wrong exe started?** Set the `BRYCE_EXE` variable to the full Linux path of the executable, e.g. `/config/wine/drive_c/Program Files/.../Bryce 3D.exe`.
- **Logs.** In Unraid, use the container's *Logs* button. Lines from this setup start with `[bryce3d]`.
