#!/usr/bin/env python3
"""sdf2bryce: turn a PubChem SDF/MOL file into a 3D model Bryce 3D can import.

Writes a space-filling model (atoms at their van der Waals size; ball-and-stick
and sticks are available too) as
  - <name>.3ds          3D Studio, one named object + material per element
  - <name>.obj/.mtl     Wavefront OBJ, one group + material per element
Atoms use the standard CPK/Jmol colours. Each bond is split at its middle and
each half is coloured like the atom it touches. Every element becomes one
part, so you can recolour all the carbons in Bryce with a single click.

Usage:
  sdf2bryce.py molecule.sdf [-o OUTDIR] [--style spacefill|ballstick|sticks]
                            [--quality low|medium|high|ultra] [--no-hydrogens]
                            [--scale N] [--format 3ds,obj]
  sdf2bryce.py --watch DIR      convert every new/changed .sdf/.mol in DIR

No third-party packages are needed (Python 3 standard library only).
"""
import argparse
import math
import os
import struct
import sys
import time

# ---------------------------------------------------------------- element data
# CPK colours as used by Jmol, and van der Waals radii (Angstrom, Bondi/Alvarez).
CPK = {
    "H": (0xFF, 0xFF, 0xFF), "He": (0xD9, 0xFF, 0xFF), "Li": (0xCC, 0x80, 0xFF),
    "B": (0xFF, 0xB5, 0xB5), "C": (0x90, 0x90, 0x90), "N": (0x30, 0x50, 0xF8),
    "O": (0xFF, 0x0D, 0x0D), "F": (0x90, 0xE0, 0x50), "Na": (0xAB, 0x5C, 0xF2),
    "Mg": (0x8A, 0xFF, 0x00), "Al": (0xBF, 0xA6, 0xA6), "Si": (0xF0, 0xC8, 0xA0),
    "P": (0xFF, 0x80, 0x00), "S": (0xFF, 0xFF, 0x30), "Cl": (0x1F, 0xF0, 0x1F),
    "K": (0x8F, 0x40, 0xD4), "Ca": (0x3D, 0xFF, 0x00), "Fe": (0xE0, 0x66, 0x33),
    "Co": (0xF0, 0x90, 0xA0), "Ni": (0x50, 0xD0, 0x50), "Cu": (0xC8, 0x80, 0x33),
    "Zn": (0x7D, 0x80, 0xB0), "Se": (0xFF, 0xA1, 0x00), "Br": (0xA6, 0x29, 0x29),
    "I": (0x94, 0x00, 0x94), "Pt": (0xD0, 0xD0, 0xE0), "Au": (0xFF, 0xD1, 0x23),
    "Hg": (0xB8, 0xB8, 0xD0), "Mn": (0x9C, 0x7A, 0xC7), "Cr": (0x8A, 0x99, 0xC7),
}
DEFAULT_COLOR = (0xFF, 0x14, 0x93)
VDW = {
    "H": 1.10, "He": 1.40, "Li": 1.82, "B": 1.92, "C": 1.70, "N": 1.55, "O": 1.52,
    "F": 1.47, "Na": 2.27, "Mg": 1.73, "Al": 1.84, "Si": 2.10, "P": 1.80, "S": 1.80,
    "Cl": 1.75, "K": 2.75, "Ca": 2.31, "Fe": 2.04, "Co": 2.00, "Ni": 1.63, "Cu": 1.40,
    "Zn": 1.39, "Se": 1.90, "Br": 1.85, "I": 1.98, "Pt": 1.75, "Au": 1.66, "Hg": 1.55,
    "Mn": 2.05, "Cr": 2.06,
}
DEFAULT_VDW = 1.8

QUALITY = {  # (geodesic sphere subdivisions, cylinder sides); triangles per sphere = 20 * 4**n
    "low": (2, 8),        #    320 triangles per atom
    "medium": (3, 16),    #  1,280
    "high": (4, 32),      #  5,120
    "ultra": (5, 48),     # 20,480
}


# ---------------------------------------------------------------- vector maths
def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def norm(a): return math.sqrt(dot(a, a))
def unit(a):
    n = norm(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-9 else (0.0, 0.0, 1.0)


def any_perpendicular(v):
    other = (1.0, 0.0, 0.0) if abs(v[0]) < 0.9 else (0.0, 1.0, 0.0)
    return unit(cross(v, other))


# ---------------------------------------------------------------- SDF parsing
class Molecule:
    def __init__(self, name):
        self.name = name
        self.atoms = []   # (element, (x, y, z))
        self.bonds = []   # (i, j, order) zero-based
        self.dims = ""


def parse_sdf(path):
    """Parse the first molecule of a V2000 or V3000 MOL/SDF file."""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    if len(lines) < 4:
        raise ValueError("file is too short to be an SDF/MOL file")
    mol = Molecule(lines[0].strip() or os.path.splitext(os.path.basename(path))[0])
    # Header line 2, columns 21-22, says whether coordinates are 2D or 3D.
    mol.dims = lines[1][20:22].upper() if len(lines[1]) >= 22 else ""
    counts = lines[3]
    if "V3000" in counts:
        mode = None
        for line in lines[4:]:
            if line.startswith("M  END") or line.startswith("$$$$"):
                break
            if not line.startswith("M  V30 "):
                continue
            body = line[7:].strip()
            if body.startswith("BEGIN ATOM"):
                mode = "atom"
            elif body.startswith("BEGIN BOND"):
                mode = "bond"
            elif body.startswith("END"):
                mode = None
            elif mode == "atom":
                p = body.split()
                mol.atoms.append((norm_element(p[1]), (float(p[2]), float(p[3]), float(p[4]))))
            elif mode == "bond":
                p = body.split()
                mol.bonds.append((int(p[2]) - 1, int(p[3]) - 1, int(p[1])))
    else:
        n_atoms, n_bonds = int(counts[0:3]), int(counts[3:6])
        for line in lines[4:4 + n_atoms]:
            p = line.split()
            mol.atoms.append((norm_element(p[3]), (float(p[0]), float(p[1]), float(p[2]))))
        for line in lines[4 + n_atoms:4 + n_atoms + n_bonds]:
            a, b, order = int(line[0:3]), int(line[3:6]), int(line[6:9])
            mol.bonds.append((a - 1, b - 1, order))
    if not mol.atoms:
        raise ValueError("no atoms found")
    return mol


def norm_element(sym):
    sym = sym.strip()
    return sym[:1].upper() + sym[1:].lower()


# ---------------------------------------------------------------- mesh building
_ICO_CACHE = {}


def unit_icosphere(level):
    """Geodesic sphere of radius 1: evenly sized triangles, no bunching at poles."""
    if level in _ICO_CACHE:
        return _ICO_CACHE[level]
    t = (1 + math.sqrt(5)) / 2
    verts = [unit(v) for v in [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0),
                               (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
                               (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]]
    faces = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
             (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
             (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
             (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    for _ in range(level):
        mid, new = {}, []

        def midpoint(a, b):
            key = (a, b) if a < b else (b, a)
            if key not in mid:
                mid[key] = len(verts)
                verts.append(unit(mul(add(verts[a], verts[b]), 0.5)))
            return mid[key]

        for a, b, c in faces:
            ab, bc, ca = midpoint(a, b), midpoint(b, c), midpoint(c, a)
            new += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = new
    _ICO_CACHE[level] = (verts, faces)
    return verts, faces


class Mesh:
    """Triangles grouped by element. parts[element] = (vertices, normals, faces)."""

    def __init__(self):
        self.parts = {}

    def part(self, element):
        return self.parts.setdefault(element, ([], [], []))

    def sphere(self, element, center, radius, level):
        verts, normals, faces = self.part(element)
        base = len(verts)
        uv, uf = unit_icosphere(level)
        verts.extend(add(center, mul(v, radius)) for v in uv)
        normals.extend(uv)                       # exact sphere normals -> smooth shading
        faces.extend((a + base, b + base, c + base) for a, b, c in uf)

    def cylinder(self, element, p, q, radius, sides):
        verts, normals, faces = self.part(element)
        axis = sub(q, p)
        if norm(axis) < 1e-6:
            return
        u = any_perpendicular(unit(axis))
        w = cross(unit(axis), u)
        base = len(verts)
        for j in range(sides):
            ang = 2 * math.pi * j / sides
            dirn = add(mul(u, math.cos(ang)), mul(w, math.sin(ang)))
            off = mul(dirn, radius)
            verts.append(add(p, off))
            verts.append(add(q, off))
            normals.extend((dirn, dirn))
        for j in range(sides):
            a, b = base + 2 * j, base + 2 * j + 1
            c, d = base + 2 * ((j + 1) % sides), base + 2 * ((j + 1) % sides) + 1
            faces.append((a, c, d))
            faces.append((a, d, b))


def build(mol, style, quality, hydrogens, scale):
    level, sides = QUALITY[quality]
    keep = [hydrogens or el != "H" for el, _ in mol.atoms]
    # Centre the molecule on the origin.
    pts = [xyz for (el, xyz), k in zip(mol.atoms, keep) if k]
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    cz = sum(p[2] for p in pts) / len(pts)
    pos = [mul(sub(xyz, (cx, cy, cz)), scale) for _, xyz in mol.atoms]

    mesh = Mesh()
    bond_r = {"ballstick": 0.10, "sticks": 0.16, "spacefill": 0.0}[style] * scale
    for i, (el, _) in enumerate(mol.atoms):
        if not keep[i]:
            continue
        if style == "spacefill":
            r = VDW.get(el, DEFAULT_VDW)
        elif style == "sticks":
            r = 0.16
        else:
            r = 0.25 * VDW.get(el, DEFAULT_VDW)
        mesh.sphere(el, pos[i], r * scale, level)

    if style != "spacefill":
        neighbours = {}
        for a, b, _ in mol.bonds:
            neighbours.setdefault(a, []).append(b)
            neighbours.setdefault(b, []).append(a)
        for a, b, order in mol.bonds:
            if not (keep[a] and keep[b]):
                continue
            pa, pb = pos[a], pos[b]
            axis = unit(sub(pb, pa))
            offsets = [(0.0, bond_r)]
            if order in (2, 3) and style == "ballstick":
                perp = bond_plane(a, b, pos, neighbours, axis)
                if order == 2:
                    offsets = [(-0.09 * scale, bond_r * 0.7), (0.09 * scale, bond_r * 0.7)]
                else:
                    offsets = [(-0.13 * scale, bond_r * 0.6), (0.0, bond_r * 0.6),
                               (0.13 * scale, bond_r * 0.6)]
            else:
                perp = (0.0, 0.0, 0.0)
            mid = mul(add(pa, pb), 0.5)
            for d, r in offsets:
                o = mul(perp, d)
                mesh.cylinder(mol.atoms[a][0], add(pa, o), add(mid, o), r, sides)
                mesh.cylinder(mol.atoms[b][0], add(mid, o), add(pb, o), r, sides)
    return mesh


def bond_plane(a, b, pos, neighbours, axis):
    """Direction to offset a double/triple bond: in the plane of a neighbouring atom."""
    for atom, other in ((a, b), (b, a)):
        for n in neighbours.get(atom, []):
            if n == other:
                continue
            v = sub(pos[n], pos[atom])
            perp = sub(v, mul(axis, dot(v, axis)))
            if norm(perp) > 1e-3:
                return unit(perp)
    return any_perpendicular(axis)


# ---------------------------------------------------------------- writers
def write_obj(mesh, path, name):
    mtl = os.path.splitext(path)[0] + ".mtl"
    with open(mtl, "w", newline="\r\n") as f:
        f.write(f"# {name} - materials (CPK colours)\n")
        for el in mesh.parts:
            r, g, b = (c / 255 for c in CPK.get(el, DEFAULT_COLOR))
            f.write(f"newmtl {el}\nKa {r:.3f} {g:.3f} {b:.3f}\nKd {r:.3f} {g:.3f} {b:.3f}\n"
                    f"Ks 0.300 0.300 0.300\nNs 60\nd 1\nillum 2\n\n")
    with open(path, "w", newline="\r\n") as f:
        f.write(f"# {name} - made by sdf2bryce\nmtllib {os.path.basename(mtl)}\n")
        offset = 1
        for el, (verts, normals, faces) in mesh.parts.items():
            f.write(f"o {el}\ng {el}\nusemtl {el}\ns 1\n")
            f.write("".join(f"v {v[0]:.5f} {v[1]:.5f} {v[2]:.5f}\n" for v in verts))
            f.write("".join(f"vn {n[0]:.5f} {n[1]:.5f} {n[2]:.5f}\n" for n in normals))
            f.write("".join(f"f {a + offset}//{a + offset} {b + offset}//{b + offset} "
                            f"{c + offset}//{c + offset}\n" for a, b, c in faces))
            offset += len(verts)


def chunk(cid, *payload):
    data = b"".join(payload)
    return struct.pack("<HI", cid, 6 + len(data)) + data


def write_3ds(mesh, path):
    materials = []
    for el in mesh.parts:
        rgb = bytes(CPK.get(el, DEFAULT_COLOR))
        materials.append(chunk(0xAFFF,
                               chunk(0xA000, el.encode() + b"\0"),
                               chunk(0xA010, chunk(0x0011, rgb)),
                               chunk(0xA020, chunk(0x0011, rgb)),
                               chunk(0xA030, chunk(0x0011, bytes((0x4C, 0x4C, 0x4C))))))
    objects = []
    for el, (verts, _normals, faces) in mesh.parts.items():
        # A 3DS mesh holds at most 65535 vertices and 65535 faces: split big parts.
        pieces, start = [], 0
        while start < len(faces):
            used, remap, out_f = [], {}, []
            i = start
            # 3DS stores vertex and face counts as 16-bit numbers.
            while i < len(faces) and len(used) <= 65532 and len(out_f) < 65535:
                for v in faces[i]:
                    if v not in remap:
                        remap[v] = len(used)
                        used.append(v)
                out_f.append(tuple(remap[v] for v in faces[i]))
                i += 1
            pieces.append((used, out_f))
            start = i
        for n, (used, out_f) in enumerate(pieces):
            oname = (el if n == 0 else f"{el}_{n + 1}")[:10]
            pts = b"".join(struct.pack("<3f", *verts[v]) for v in used)
            fdata = b"".join(struct.pack("<4H", a, b, c, 7) for a, b, c in out_f)
            matgroup = chunk(0x4130, el.encode() + b"\0", struct.pack("<H", len(out_f)),
                             b"".join(struct.pack("<H", k) for k in range(len(out_f))))
            smooth = chunk(0x4150, struct.pack("<I", 1) * len(out_f))
            trimesh = chunk(0x4100,
                            chunk(0x4110, struct.pack("<H", len(used)), pts),
                            chunk(0x4120, struct.pack("<H", len(out_f)), fdata, matgroup, smooth),
                            chunk(0x4160, struct.pack("<12f", 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0)))
            objects.append(chunk(0x4000, oname.encode() + b"\0", trimesh))
    editor = chunk(0x3D3D, chunk(0x3D3E, struct.pack("<I", 3)), *materials,
                   chunk(0x0100, struct.pack("<f", 1.0)), *objects)
    with open(path, "wb") as f:
        f.write(chunk(0x4D4D, chunk(0x0002, struct.pack("<I", 3)), editor))


# ---------------------------------------------------------------- driver
def convert(src, outdir=None, style="spacefill", quality="high", hydrogens=True,
            scale=1.0, formats=("3ds", "obj")):
    mol = parse_sdf(src)
    flat = all(abs(xyz[2]) < 1e-4 for _, xyz in mol.atoms)
    if mol.dims == "2D" or (mol.dims != "3D" and flat and len(mol.atoms) > 3):
        print(f"warning: {os.path.basename(src)} is flat (2D). On PubChem, download the "
              f"'3D Conformer' SDF for a real 3D shape.", file=sys.stderr)
    mesh = build(mol, style, quality, hydrogens, scale)
    outdir = outdir or os.path.dirname(os.path.abspath(src))
    os.makedirs(outdir, exist_ok=True)
    base = os.path.join(outdir, os.path.splitext(os.path.basename(src))[0])
    written = []
    if "3ds" in formats:
        write_3ds(mesh, base + ".3ds")
        written.append(base + ".3ds")
    if "obj" in formats:
        write_obj(mesh, base + ".obj", mol.name)
        written += [base + ".obj", base + ".mtl"]
    tris = sum(len(f) for _, _, f in mesh.parts.values())
    counts = {}
    for el, _ in mol.atoms:
        if hydrogens or el != "H":
            counts[el] = counts.get(el, 0) + 1
    summary = ", ".join(f"{el}x{n}" for el, n in sorted(counts.items()))
    print(f"{os.path.basename(src)}: {summary}; {tris} triangles -> "
          + ", ".join(os.path.basename(w) for w in written))
    if tris > 400_000:
        print("  note: that is a very heavy model for Bryce 3D; if importing is slow or fails, "
              "try a lower --quality or --no-hydrogens", file=sys.stderr)
    return written


def watch(folder, **opts):
    """Convert each .sdf/.mol in folder whenever it is new or changed."""
    os.makedirs(folder, exist_ok=True)
    print(f"watching {folder} for .sdf/.mol files", flush=True)
    failed = {}   # path -> mtime of the version that failed (retry once it changes)
    sig_file = os.path.join(folder, ".sdf2bryce-settings")
    sig = repr(sorted(opts.items())) + " v2"
    try:
        old_sig = open(sig_file).read()
    except OSError:
        old_sig = None
    redo = set()
    if old_sig != sig:
        redo = {fn for fn in os.listdir(folder) if fn.lower().endswith((".sdf", ".mol"))}
        if old_sig is not None and redo:
            print("settings changed: re-converting all molecules", flush=True)
        try:
            with open(sig_file, "w") as f:
                f.write(sig)
        except OSError:
            pass
    while True:
        for fn in sorted(os.listdir(folder)):
            if not fn.lower().endswith((".sdf", ".mol")):
                continue
            src = os.path.join(folder, fn)
            out = os.path.splitext(src)[0] + (".3ds" if "3ds" in opts["formats"] else ".obj")
            try:
                if (fn not in redo and os.path.exists(out)
                        and os.path.getmtime(out) >= os.path.getmtime(src)):
                    continue
                mtime = os.path.getmtime(src)
                if failed.get(src) == mtime or time.time() - mtime < 2:   # bad, or still copying
                    continue
                redo.discard(fn)
                convert(src, **opts)
            except Exception as e:  # keep watching even if one file is bad
                print(f"{fn}: could not convert: {e}", file=sys.stderr, flush=True)
                failed[src] = os.path.getmtime(src)
            sys.stdout.flush()
        time.sleep(5)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help=".sdf or .mol files")
    ap.add_argument("-o", "--outdir", help="output folder (default: next to the input)")
    ap.add_argument("--style", choices=["spacefill", "ballstick", "sticks"], default="spacefill")
    ap.add_argument("--quality", choices=list(QUALITY), default="high")
    ap.add_argument("--no-hydrogens", action="store_true")
    ap.add_argument("--scale", type=float, default=1.0, help="model units per Angstrom")
    ap.add_argument("--format", default="3ds,obj", help="comma list: 3ds, obj")
    ap.add_argument("--watch", metavar="DIR", help="keep converting files dropped into DIR")
    a = ap.parse_args()
    opts = dict(outdir=a.outdir, style=a.style, quality=a.quality,
                hydrogens=not a.no_hydrogens, scale=a.scale,
                formats=tuple(f.strip().lower() for f in a.format.split(",")))
    if a.watch:
        opts.pop("outdir")
        watch(a.watch, **opts)
    if not a.files:
        ap.error("give one or more .sdf files, or --watch DIR")
    status = 0
    for f in a.files:
        try:
            convert(f, **opts)
        except Exception as e:
            print(f"{f}: could not convert: {e}", file=sys.stderr)
            status = 1
    sys.exit(status)


if __name__ == "__main__":
    main()
