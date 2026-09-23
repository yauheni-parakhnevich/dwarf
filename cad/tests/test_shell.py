"""What the assembled shell has to be true of. Skipped until `build.py statue assemble` has run.

These are slow by the standards of the rest of the suite - several run manifold booleans on a
quarter of a million triangles - so every mesh is loaded once per session and the derived solids,
the bell above all, are cached with it.

The shell is now the statue: a reconstruction hollowed and cut into three fixed pieces around the
belt, two side panels with the sleeves on them, two mitten caps, and a bell - beard, face and hat
in one - that turns on the shroud. Most of what follows is about that bell: it has to turn to its
stops without touching anything, and the jet has to leave through it at every tilt.
"""
import itertools
import math
from pathlib import Path

import numpy as np
import pytest
import trimesh

import params as P

CAD = Path(__file__).resolve().parents[1]
STL = CAD / "out" / "stl"
STATUE = CAD / "out" / "statue"
ENGINE = "manifold"
SECTIONS = tuple(P.SECTIONS_STATUE)
BELL = ("beard", "head", "hat")
FIXED = ("base_left", "base_right", "hand_left", "hand_right", "torso", "panel_left", "panel_right")
# Sections are cut from one shell along planes, so neighbours share faces and no volume. The
# budget is for the two microns each pinched vertex was moved by before the file was written.
SHARED_MM3 = 5.0

pytestmark = pytest.mark.skipif(not (STL / "torso.stl").exists() or not (STATUE / "cavity_grown.stl").exists(),
                                reason="run `build.py mech statue assemble` first")


@pytest.fixture(scope="session")
def sections():
    return {n: trimesh.load(STL / f"{n}.stl") for n in SECTIONS}


@pytest.fixture(scope="session")
def bell(sections):
    """Beard, face and hat as the one solid that turns."""
    return trimesh.boolean.union([sections[n] for n in BELL], engine=ENGINE)


@pytest.fixture(scope="session")
def still(sections):
    """Everything that does not turn, as one solid."""
    return trimesh.boolean.union([sections[n] for n in FIXED], engine=ENGINE)


def volume_of(mesh):
    return 0.0 if mesh is None or mesh.is_empty else abs(mesh.volume)


def clash(a, b):
    return volume_of(trimesh.boolean.intersection([a, b], engine=ENGINE))


def turned(mesh, deg):
    out = mesh.copy()
    out.apply_transform(trimesh.transformations.rotation_matrix(math.radians(deg), (0.0, 0.0, 1.0)))
    return out


def hits(mesh, origin, direction, limit=None):
    """Where a ray first meets a mesh, as a distance, or None."""
    loc, _, _ = mesh.ray.intersects_location(np.array([origin], float), np.array([direction], float))
    if not len(loc):
        return None
    d = min(float(np.linalg.norm(np.array(p) - np.array(origin))) for p in loc)
    return d if limit is None or d <= limit else None


# --- the pieces themselves --------------------------------------------------------------------
@pytest.mark.parametrize("name", SECTIONS)
def test_every_section_is_a_solid(sections, name):
    m = sections[name]
    assert m.is_watertight, f"{name} is not watertight"
    assert m.is_winding_consistent, f"{name} has inconsistent winding"
    assert m.volume > 0.0, f"{name} has no volume"
    assert m.body_count == 1, f"{name} is {m.body_count} bodies, not one printable piece"


@pytest.mark.parametrize("name", SECTIONS)
def test_every_section_fits_the_bed(sections, name):
    e = sections[name].extents
    assert max(e) <= P.BED, f"{name} is {max(e):.1f} mm across; the bed is {P.BED}"


@pytest.mark.parametrize("pair", sorted(itertools.combinations(SECTIONS, 2)))
def test_no_two_sections_share_a_millimetre(sections, pair):
    a, b = pair
    if not np.all(sections[a].bounds[0] <= sections[b].bounds[1] + 1.0):
        return                                    # their bounding boxes do not even meet
    v = clash(sections[a], sections[b])
    assert v <= SHARED_MM3, f"{a} and {b} share {v:.1f} mm3"


# --- the interface parts ----------------------------------------------------------------------
def test_every_interface_part_is_welded_into_its_section(sections):
    """What the assembler clipped into a section has to be inside that section."""
    import assemble as A

    grown = trimesh.load(STATUE / "cavity_grown.stl")
    seen = 0
    for name, targets in A.INTO.items():
        if not (STL / f"{name}.stl").exists():
            continue
        for target in targets:
            raw = trimesh.load(STATUE / "raw" / f"{target}.stl")
            for piece in A.blanks(target, raw, grown):
                seen += 1
                outside = volume_of(trimesh.boolean.difference(
                    [piece, sections[target]], engine=ENGINE))
                assert outside <= 0.02 * abs(piece.volume) + 50.0, (
                    f"{name}: {outside / 1e3:.2f} cm3 of it stands outside {target}")
    assert seen, "no interface part was found at all"


# --- the openings -----------------------------------------------------------------------------
def test_the_window_is_open(sections):
    z = P.Z_LENS + P.WINDOW_Z_BIAS
    assert hits(sections["torso"], (0.0, P.CAM_Y, z), (1.0, 0.0, 0.0)) is None, \
        "the camera looks at the inside of the coat"
    for dy, dz in ((P.WINDOW_W / 2 + 6.0, 0.0), (-P.WINDOW_W / 2 - 6.0, 0.0),
                   (0.0, -P.WINDOW_H / 2 - 8.0)):
        assert hits(sections["torso"], (0.0, P.CAM_Y + dy, z + dz), (1.0, 0.0, 0.0)) is not None, \
            "the window is bigger than it was asked to be"
    # above it there is barely any ring left: the window's top edge and the ring's top are
    # 1.7 mm apart, which is the thinnest the fixed shell gets anywhere.
    top = z + P.WINDOW_H / 2
    assert P.Z_TURN - P.TURN_GAP - top >= 1.0, (
        f"only {P.Z_TURN - P.TURN_GAP - top:.1f} mm of coat is left over the window")


def test_the_vents_are_open(sections):
    assert hits(sections["torso"], (0.0, 0.0, P.Z_VENT_IN), (-1.0, 0.0, 0.0)) is None, \
        "the intake is blocked"
    x, z = P.FAN_XZ
    side = 1.0 if P.FAN_PANEL == "left" else -1.0
    panel = sections[f"panel_{P.FAN_PANEL}"]
    # From the fan's own plane out through the sleeve's skin. There is no second probe beside it
    # here, as there is at the window: the sleeve is not a flat. Over the fan's own disc the skin
    # wanders between y 91 and 114 and the panel does not cover all of it, so a ray four
    # millimetres to the side of the bore misses the statue rather than proving anything.
    assert hits(panel, (x, side * P.FAN_Y, z), (0.0, side, 0.0)) is None, "the exhaust is blocked"
    assert abs(P.FAN_Y) > P.PANEL_Y, "the fan sits inboard of the panel's own edge"


def test_the_mouth_and_the_parting_are_open(sections):
    head = sections["head"]
    assert hits(head, P.NOZZLE_PIVOT, (1.0, 0.0, 0.0)) is None, "the mouth is blocked"
    for deg in (P.TILT_STOP[0], 0.0, P.TILT_STOP[1]):
        a = math.radians(deg)
        d = (math.cos(a), 0.0, math.sin(a))
        origin = (P.NOZZLE_PIVOT[0] + 2.0 * d[0], 0.0, P.NOZZLE_PIVOT[2] + 2.0 * d[2])
        blocked = [n for n in ("beard", "head") if hits(sections[n], origin, d) is not None]
        assert not blocked, f"the parting is closed at {deg:+.0f} deg by {blocked}"


def test_the_shroud_screws_reach_their_bosses(sections):
    """Four radial screws through the bell, into the shroud that carries it."""
    shroud = trimesh.load(STL / "neck_shroud.stl")
    head = sections["head"]
    for deg in P.SHROUD_SCREW_ANGLES:
        a = math.radians(deg)
        out = (math.cos(a), math.sin(a), 0.0)
        start = (300.0 * out[0], 300.0 * out[1], P.SHROUD_SCREWS_Z)
        inward = (-out[0], -out[1], 0.0)
        assert hits(head, start, inward) is None, f"the screw at {deg:.0f} deg has no hole"
        d = hits(shroud, start, inward)
        assert d is not None, f"the screw at {deg:.0f} deg meets no boss on the shroud"
        assert 300.0 - d >= P.SHROUD_R_OUT - 1.0, f"the screw at {deg:.0f} deg lands inside the shroud"


# --- the bell turns ----------------------------------------------------------------------------
@pytest.mark.parametrize("deg", (-P.PAN_STOP_DEG, -30.0, 0.0, 30.0, P.PAN_STOP_DEG))
def test_the_bell_turns_to_its_stops(bell, still, deg):
    v = clash(turned(bell, deg), still)
    assert v <= SHARED_MM3, f"the bell fouls the fixed shell by {v:.1f} mm3 at {deg:+.0f} deg"


def test_the_bells_rim_stays_between_its_neighbours(sections, bell):
    lo = bell.bounds[0][2]
    assert lo >= P.Z_TURN - 0.01, f"the bell dips to z {lo:.1f}, under Z_TURN"
    outside = trimesh.boolean.intersection(
        [bell, trimesh.creation.box(extents=(2000.0, 2000.0 - 2 * P.PANEL_Y, 2000.0),
                                    transform=trimesh.transformations.translation_matrix(
                                        (0.0, 1000.0 + P.PANEL_Y, 0.0)))], engine=ENGINE)
    if volume_of(outside) > SHARED_MM3:
        assert outside.bounds[0][2] >= P.PANEL_TOP - 0.01, (
            f"the bell reaches z {outside.bounds[0][2]:.1f} outside the panels, "
            f"whose tops are at {P.PANEL_TOP}")


# --- the jet -----------------------------------------------------------------------------------
def _jet_rays(deg, n=9, seed=5):
    """The jet's envelope leaving the nozzle: a JET_D disc of rays along the arm's line."""
    a = math.radians(deg)
    d = np.array([math.cos(a), 0.0, math.sin(a)])
    tip = np.array([P.NOZZLE_PIVOT[0], 0.0, P.NOZZLE_PIVOT[2]]) + d * P.NOZZLE_ARM_L
    up = np.cross(d, [0.0, 1.0, 0.0])
    rng = np.random.default_rng(seed)
    r = P.JET_D / 2 * np.sqrt(rng.uniform(0.0, 1.0, n))
    th = rng.uniform(0.0, 2 * math.pi, n)
    pts = tip + np.outer(r * np.cos(th), up) + np.outer(r * np.sin(th), [0.0, 1.0, 0.0])
    return pts, np.tile(d, (n, 1))


@pytest.mark.parametrize("deg", tuple(np.arange(P.TILT_STOP[0], P.TILT_STOP[1] + 1, 5.0)))
def test_the_jet_leaves_the_statue(sections, deg):
    """Nothing of the shell stands in the jet's way, at any tilt the firmware allows."""
    origins, dirs = _jet_rays(deg)
    for name in ("beard", "head", "torso", "panel_left", "panel_right"):
        loc, idx, _ = sections[name].ray.intersects_location(origins, dirs)
        assert not len(loc), f"the jet at {deg:+.0f} deg hits {name}"
