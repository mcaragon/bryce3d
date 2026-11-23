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

- **Screen size.** The default is 1024×768. The screen is fixed: the browser shows it at its real size, pixel for pixel, and only shrinks it if your window is too small. It never stretches it to fit the window, because Bryce can't cope with a screen that changes size. Bryce fills the screen with black and puts its interface in the middle, just as it did on Windows 95. To make the scene view bigger, use *File → Document Setup*; for example, 800×600 or 800×450 (16:9) works well on a 1024×768 screen. To change the screen size, set `DISPLAY_WIDTH` / `DISPLAY_HEIGHT`; 640×480, 800×600 and 1024×768 suit Bryce 3D. Set `ALLOW_REMOTE_RESIZE=1` to let the browser resize the screen again.
- **Big renders.** The document size is also the size of the view you edit in. Edit at a size that fits the screen with the shape you want, then use *File → Render to Disk* to render at full size, e.g. 1920×1080.
- **Where's the menu bar?** Bryce 3D hides its `File | Edit | Objects | Help` menu bar until you move the mouse to the very top edge of the screen, just as it did on Windows 95.
- **Sharp scaling.** Off by default. Set `SHARP_SCALING=1` for blocky, crisp pixels when the browser enlarges a small screen, e.g. 640×480 on a big monitor. It makes text look uneven when the screen is shrunk or enlarged by an amount that isn't a whole multiple.
- **Preset pop-ups.** Bryce opens its preset libraries (the arrows next to Create, Edit and Sky & Fog) when the button goes down and closes them when it comes up. On a modern machine they appear so fast that a normal click closes them again. A small proxy (`rootfs/opt/bryce3d/rfb_click_proxy.py`) sits between the web UI and the VNC server and turns a click on those arrows into a quick press and release, so the pop-up stays open. Set `CLICK_FIX=0` to turn it off. Note that port 5900 (raw VNC) connects directly and does not get this fix.
- **Dialogs and palettes.** Bryce's palettes and dialogs are separate windows. The base image's window manager would normally stretch every window to full screen and push it to the back. This image turns that rule off, and also sets Wine's `UseTakeFocus=N` so dialogs receive keyboard input.
- **Bryce render resolution.** Use *File → Document Setup*, then save a scene named `DEFAULT` in the Bryce folder so it opens at that size every time.
- **Clipboard / file transfer.** Open the noVNC side panel (the arrow on the left edge). Exchanging files through the share (drive E:) is the easiest route.
- **Password.** The UI has no login by default. Keep it on your LAN, or set `WEB_AUTHENTICATION=1` with a username and password. That also needs `SECURE_CONNECTION=1` (HTTPS) or `WEB_AUTHENTICATION_ALLOW_INSECURE=1`.
- **Reinstall from scratch.** Stop the container and delete `/mnt/user/appdata/bryce3d/wine`. To use a different ISO, also delete `.../cdrom`.
- **Wrong exe started?** Set the `BRYCE_EXE` variable to the full Linux path of the executable, e.g. `/config/wine/drive_c/Program Files/.../Bryce 3D.exe`.
- **Installer windows hidden?** Dialogs can get stuck behind the installer's full-screen background. List the open windows with `docker exec bryce3d sh -c 'DISPLAY=:0 xdotool search --name .'` and bring one to the front with `docker exec bryce3d sh -c 'DISPLAY=:0 xdotool search --name "^Welcome$" windowraise windowactivate'`.
- **Logs.** In Unraid, use the container's *Logs* button. Lines from this setup start with `[bryce3d]`.

## Molecules from PubChem

The container can turn PubChem structure files into colored 3D models for Bryce. By default it makes both a space-filling model and a ball-and-stick model of each molecule:

1. On the compound's PubChem page, go to *Download → 3D Conformer → SDF*. Use the **3D** file: a 2D file comes out flat.
2. Copy the `.sdf` into a `molecules` folder in your `bryce3d` share, e.g. `\\UNRAID\bryce3d\molecules\`. The container creates the folder on start.
3. Within a few seconds, `name-spacefill.3ds` and `name-ballstick.3ds` appear next to it, each with matching `.obj` and `.mtl` files.
4. In Bryce, use *File → Import Object* and open `E:\molecules\name-spacefill.3ds` or `E:\molecules\name-ballstick.3ds`. If that doesn't keep the colors, try the `.obj`.

In the space-filling model, each atom is a sphere at its van der Waals size. In the ball-and-stick model, atoms are a quarter of that size and bonds are sticks; double and triple bonds show as parallel sticks, and each half of a bond takes the color of the atom it touches. Both versions of a molecule come out in the same position, so they line up exactly. Every molecule comes out in the same standard pose (see `MOLECULE_ORIENT` below). Import all of them in the same format, all `.3ds` or all `.obj`, because Bryce may treat the two formats' axes differently. Each element is a separate, named part with a standard CPK color: carbon gray, oxygen red, nitrogen blue, hydrogen white, and so on. If Bryce doesn't keep the colors, each element still arrives as one part. Select it and pick a color in the *Materials Lab*: that's one click per element, not one per atom.

Template settings (under *Show more settings*):

| Variable | Default | Meaning |
|---|---|---|
| `MOLECULE_STYLE` | `spacefill,ballstick` | Which models to make, comma-separated: `spacefill`, `ballstick` and/or `sticks`. With a single style, files have no suffix, e.g. `caffeine.3ds`. |
| `MOLECULE_QUALITY` | `high` | How smooth the atoms are: `low` (320 triangles per atom), `medium` (1,280), `high` (5,120) or `ultra` (20,480). Atoms are geodesic spheres and the files carry smooth-shading data. At `high`, a 50-atom molecule is about 250k triangles; at `ultra`, about 1M. |
| `MOLECULE_ORIENT` | `standard` | `standard` puts every molecule in the same pose: centred, longest side along X (left-right), next along Y (up), flattest side facing the camera along Z. It only rotates, never mirrors, so chirality is kept. `original` keeps the orientation from the PubChem file. |
| `MOLECULE_HYDROGENS` | `1` | `0` leaves hydrogen atoms out |
| `MOLECULE_WATCH` | `1` | `0` turns the automatic converter off |

To use other settings for one molecule, run the converter by hand. Paths are inside the container, and `/storage` is your share:

```bash
docker exec bryce3d sdf2bryce /storage/molecules/caffeine.sdf --quality ultra
```

`sdf2bryce --help` lists all the options. After you change the template settings and restart the container, every molecule in the folder is re-converted automatically. To redo just one, delete its `.3ds`.

## Credits

The 640×480 plain-window setup, the hidden-menu-bar tip and the idea and coordinates for the pop-up click fix come from [RaymonDev/BryceDock](https://github.com/RaymonDev/BryceDock), another project that runs Bryce 3D in Docker.
