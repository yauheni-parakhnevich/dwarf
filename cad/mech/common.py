import math
from pathlib import Path
from build123d import (Axis, Box, Compound, Cylinder, Location, Plane, Polygon, Pos, Rot, Part,
                       export_step, export_stl, mirror, revolve)
import params as P
from mech import ALL

OUT = Path(__file__).resolve().parents[1] / "out"
STEP = OUT / "step"
STL = OUT / "stl"


def export(part: Part, name: str) -> None:
    STEP.mkdir(parents=True, exist_ok=True)
    STL.mkdir(parents=True, exist_ok=True)
    if not export_step(part, str(STEP / f"{name}.step")):
        raise RuntimeError(f"STEP export failed: {name}")
    # 0.05 mm chordal tolerance: coarser than build123d's default, fine for a 0.6 mm nozzle
    if not export_stl(part, str(STL / f"{name}.stl"), tolerance=0.05, angular_tolerance=0.1):
        raise RuntimeError(f"STL export failed: {name}")


def polar(r, deg):
    """(x, y) at radius r, `deg` round from +X."""
    return r * math.cos(math.radians(deg)), r * math.sin(math.radians(deg))


def skin_solid(profile, inset=0.0):
    """The solid of revolution `inset` millimetres inside a shell profile's skin.

    Inset 0 is the skin itself; WALL - 1.2 is the surface ring_r_out puts an interface part on,
    so a part clipped to it is embedded 1.2 mm into the wall and never stands proud; WALL is the
    wall's inner face; WALL + 1 the cavity with a millimetre to spare.
    """
    pts = [(P.shell_r(profile, z) - inset, z) for _, z in profile]
    z0, z1 = profile[0][1], profile[-1][1]
    return revolve(Plane.XZ * Polygon((0.0, z0), *pts, (0.0, z1)), axis=Axis.Z)


def cyl_z(r, z0, z1, x=0.0, y=0.0):
    """A cylinder along Z from z0 to z1."""
    return Pos(x, y, (z0 + z1) / 2) * Cylinder(r, z1 - z0)


def cyl_y(r, y0, y1, x=0.0, z=0.0):
    return Pos(x, (y0 + y1) / 2, z) * Rot(90, 0, 0) * Cylinder(r, y1 - y0)


def cyl_x(r, x0, x1, y=0.0, z=0.0):
    return Pos((x0 + x1) / 2, y, z) * Rot(0, 90, 0) * Cylinder(r, x1 - x0)


def box(x0, x1, y0, y1, z0, z1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)


def servo_body(spec, shaft_xyz, axis="z", up=True):
    """A servo as a solid, for clearance checks and cutters.

    `shaft_xyz` is where the output shaft leaves the body and `axis` is the shaft direction.
    Only the orientations this design uses exist:
    "-z": shaft down, body above the shaft face, length running +X from the shaft end (pan);
    "y":  shaft along +Y, body behind the shaft face, length running +Z from the shaft end; with
          up=False it runs -Z instead, which is how the nozzle's micro servo hangs.
    """
    L, W, H = spec["body"]
    off = spec["shaft_off"]
    sx, sy, sz = shaft_xyz
    if axis == "-z":
        return box(sx - off, sx + (L - off), sy - W / 2, sy + W / 2, sz, sz + H)
    if axis == "y":
        if up:
            return box(sx - W / 2, sx + W / 2, sy - H, sy, sz - off, sz + (L - off))
        return box(sx - W / 2, sx + W / 2, sy - H, sy, sz - (L - off), sz + off)
    raise ValueError(axis)


def phone_body():
    """The iPhone standing upright, camera end down, screen facing -X, centred; its camera is at CAM_Y."""
    return box(P.PHONE_FRONT_X, P.PHONE_BACK_X,
               P.PHONE_Y_OFFSET - P.PHONE_W / 2, P.PHONE_Y_OFFSET + P.PHONE_W / 2,
               P.PHONE_BOTTOM_Z, P.PHONE_BOTTOM_Z + P.PHONE_L)


def insert_holes(part, points, depth=P.INSERT_DEPTH, r=P.INSERT_D / 2, direction="down"):
    """Blind holes for heat-set inserts, drilled from each (x, y, z) point."""
    for x, y, z in points:
        if direction == "down":
            part = part - cyl_z(r, z - depth, z + 0.01, x, y)
        elif direction == "up":
            part = part - cyl_z(r, z - 0.01, z + depth, x, y)
        else:
            raise ValueError(direction)
    return part


def assembly(parts: dict) -> Compound:
    """Every part carried from its print frame to where it sits, each child carrying its name.

    The stop pin is the one thing this still knows by name: it is printed once and fitted
    twice, and a mirror is not a Location, so it cannot be declared as a placement.
    """
    at = {spec.name: spec.placement for spec in ALL}
    children = []
    for name, p in parts.items():
        child = at.get(name, Location()) * p
        child.label = name
        children.append(child)
        if name == "stop_pin":
            twin = mirror(child, about=Plane.XZ)
            twin.label = name + "_mirrored"
            children.append(twin)
    return Compound(children=children)
