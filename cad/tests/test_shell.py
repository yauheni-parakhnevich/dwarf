"""What the assembled shell has to be true of. Skipped until `build.py assemble` has run.

These are slow by the standards of the rest of the suite - a few of them run manifold booleans
on a third of a million triangles - so the meshes are loaded once per session and the derived
ones are cached too.
"""
import itertools
import math
from pathlib import Path

import numpy as np
import pytest
import trimesh

import params as P
from mech import INTERFACES

STL = Path(__file__).resolve().parents[1] / "out" / "stl"
SECTIONS = ("base", "torso", "belly", "head_back", "face", "hat")
HEAD = ("head_back", "face", "hat")
ENGINE = "manifold"

# Mech parts that stand in the head's swept space and want checking against it as it nods. Add a
# name here and the nod test takes it in without any other change. Anything on the turntable's
# plate belongs here and not in the pan test: it turns with the head, so panning moves the two
# together and only the nod moves one past the other.
EXTRA_MECH: tuple = ("neck_shroud",)

pytestmark = pytest.mark.skipif(not (STL / "belly.stl").exists(),
                                reason="run `build.py mech shell assemble` first")


@pytest.fixture(scope="session")
def sections():
    return {n: trimesh.load(STL / f"{n}.stl") for n in SECTIONS}


@pytest.fixture(scope="session")
def head_assembly(sections):
    """Everything that moves with the tilt axis, as one solid."""
    return trimesh.boolean.union([sections[n] for n in HEAD], engine=ENGINE)


def volume_of(mesh):
    return 0.0 if mesh is None or mesh.is_empty else abs(mesh.volume)


def _inside(mesh, lo, hi, n=160, seed=1):
    """Does the mesh have material anywhere in this box? Sampled, not proved."""
    rng = np.random.default_rng(seed)
    return mesh.contains(rng.uniform(lo, hi, size=(n, 3)))


def _first_radius(mesh, z, direction):
    """Where a ray leaving the axis at this height first meets the mesh, as a radius."""
    loc, _, _ = mesh.ray.intersects_location(np.array([[0.0, 0.0, z]]), np.array([direction], float))
    if not len(loc):
        return None
    return min(math.hypot(p[0], p[1]) for p in loc)


def _flies(mesh, origin, direction, distance):
    """A ray from outside flies `distance` before meeting anything: there is a hole in the way."""
    loc, _, _ = mesh.ray.intersects_location(np.array([origin], float), np.array([direction], float))
    if not len(loc):
        return True
    return float(np.linalg.norm(loc - np.array(origin, float), axis=1).min()) >= distance


# --- the meshes themselves ---------------------------------------------------------------------
def test_every_section_is_a_solid(sections):
    for n, m in sections.items():
        assert m.is_watertight, n
        assert m.is_winding_consistent, n
        assert m.volume > 0.0, n


def test_every_section_fits_the_bed(sections):
    for n, m in sections.items():
        x, y, z = m.bounds[1] - m.bounds[0]
        assert max(x, y) <= P.BED, (n, x, y)
        assert z <= P.BED, (n, z)


# --- what has to fit inside ---------------------------------------------------------------------
def test_the_wet_zone_fits_in_the_base(sections):
    base = sections["base"]
    for name, (L, W, H), (cx, cy), z0 in (
            ("canister", P.CANISTER, P.CANISTER_XY, P.CANISTER_Z0),
            ("pump", P.PUMP, P.PUMP_XY, P.PUMP_Z0),
            ("valve", P.VALVE, P.VALVE_XY, P.PUMP_Z0)):
        lo = (cx - L / 2, cy - W / 2, z0)
        hi = (cx + L / 2, cy + W / 2, z0 + H)
        assert not _inside(base, lo, hi).any(), name


def test_the_phone_fits_in_the_torso(sections):
    torso = sections["torso"]
    lo = (P.PHONE_FRONT_X - P.SLED_WALL, P.PHONE_Y_OFFSET - P.PHONE_W / 2, P.PHONE_BOTTOM_Z)
    hi = (P.LENS_FRONT_X, P.PHONE_Y_OFFSET + P.PHONE_W / 2, P.PHONE_BOTTOM_Z + P.PHONE_L)
    assert not _inside(torso, lo, hi).any()
    centre = ((lo[0] + hi[0]) / 2, P.PHONE_Y_OFFSET, P.Z_LENS + 40.0)
    for d in ((0.0, 1.0, 0.0), (0.0, -1.0, 0.0), (-1.0, 0.0, 0.0)):
        assert torso.ray.intersects_any(np.array([centre]), np.array([d]))[0], d


# --- the openings ---------------------------------------------------------------------------------
def test_the_openings_are_open(sections):
    r = P.shell_r(P.TORSO_PROFILE, P.Z_LENS) + 40.0
    z_win = P.Z_LENS + P.WINDOW_Z_BIAS
    belly = sections["belly"]
    assert _flies(belly, (r, P.CAM_Y, z_win), (-1.0, 0.0, 0.0), 60.0), "camera window"
    assert not _flies(belly, (r, P.CAM_Y - P.WINDOW_W / 2 - 12.0, z_win), (-1.0, 0.0, 0.0), 60.0), \
        "the panel beside the window"
    assert _flies(sections["face"], (P.HEAD_R + 30.0, 0.0, P.Z_MOUTH), (-1.0, 0.0, 0.0), 25.0), "mouth"
    torso = sections["torso"]
    xb = P.shell_r(P.TORSO_PROFILE, P.Z_FAN) + 30.0
    assert _flies(torso, (-xb, 0.0, P.Z_FAN), (1.0, 0.0, 0.0), 60.0), "exhaust"
    xi = P.shell_r(P.TORSO_PROFILE, P.Z_VENT_IN) + 30.0
    assert _flies(torso, (-xi, 0.0, P.Z_VENT_IN), (1.0, 0.0, 0.0), 60.0), "intake"
    xf = P.shell_r(P.BASE_PROFILE, P.Z_FILLER) + 30.0
    assert _flies(sections["base"], (-xf, 0.0, P.Z_FILLER), (1.0, 0.0, 0.0), 60.0), "filler"
    z_bot = P.Z_HEAD - P.HEAD_R
    assert _flies(sections["head_back"], (0.0, 0.0, z_bot - 30.0), (0.0, 0.0, 1.0), 60.0), "head's underside"


# --- the interface parts --------------------------------------------------------------------------
# What the assembler is allowed to take back out of a part after unioning it in, as a fraction
# of the part. Everything here is a deliberate trim, and the number is the measured one plus a
# little: a part that starts disappearing will say so.
TRIMMED = {
    "hatch_bosses": 0.10,   # cut back over a disc at each screw, so the panel keeps its full wall
    "hatch_lip": 0.08,      # the same four discs pass through the lip where it runs by a screw
    "deck_ring": 0.01,      # and through the webs, where they reach the panel at the top pair
    "ear_boss": 0.01,       # the M4 bore is drilled after the union, through the stop tab's corner
}


def test_every_interface_part_was_taken_into_its_section(sections):
    """Nothing of a part may stand outside the section it was unioned into, bar what was cut."""
    for section, names in INTERFACES.items():
        for name in names:
            part = trimesh.load(STL / f"{name}.stl")
            left = trimesh.boolean.difference([part, sections[section]], engine=ENGINE)
            budget = TRIMMED.get(name, 0.005)
            assert volume_of(left) < budget * part.volume, (section, name, volume_of(left), part.volume)


# --- the belly panel ---------------------------------------------------------------------------
def test_the_panel_and_the_torso_are_one_surface_again(sections):
    torso, belly = sections["torso"], sections["belly"]
    back = trimesh.boolean.union([torso, belly], engine=ENGINE)
    solid = [c for c in back.split(only_watertight=False) if abs(c.volume) > 1.0]
    assert len(solid) == 1, [round(c.volume, 3) for c in solid]   # welded, and nothing adrift
    loose = abs(back.volume - (torso.volume + belly.volume)) / back.volume
    assert loose < 0.01, loose                              # neither overlap nor a lost sliver


def test_the_panel_carries_its_screws_and_its_window(sections):
    belly = sections["belly"]
    for z, deg in P.HATCH_SCREWS:
        th = math.radians(deg)
        r = P.shell_r(P.TORSO_PROFILE, z) + 30.0
        o = (r * math.cos(th), r * math.sin(th), z)
        assert _flies(belly, o, (-math.cos(th), -math.sin(th), 0.0), 40.0), (z, deg)
    z_win = P.Z_LENS + P.WINDOW_Z_BIAS
    lo = (0.0, P.CAM_Y - P.WINDOW_W / 2 + 1.0, z_win - P.WINDOW_H / 2 + 1.0)
    hi = (P.BED, P.CAM_Y + P.WINDOW_W / 2 - 1.0, z_win + P.WINDOW_H / 2 - 1.0)
    assert not _inside(belly, lo, hi).any()                 # the window is empty of panel


# --- nothing is in anything else's way ---------------------------------------------------------
# The pairs that are meant to meet: the panel in the torso's own wall, the cap on the split, the
# hat on its seat. Those touch and must not overlap; every other pair must not even touch.
TOUCHING = {("torso", "belly"), ("head_back", "face"), ("head_back", "hat"), ("face", "hat")}


def _near(a, b, n=400, seed=3):
    """The closest the two meshes come, sampled from points on the first."""
    pts, _ = trimesh.sample.sample_surface(a, n, seed=seed)
    return float(trimesh.proximity.closest_point(b, pts)[1].min())


@pytest.mark.parametrize("pair", sorted(itertools.combinations(SECTIONS, 2)))
def test_no_two_sections_share_a_millimetre(sections, pair):
    a, b = (sections[n] for n in pair)
    lo = np.maximum(a.bounds[0], b.bounds[0])
    hi = np.minimum(a.bounds[1], b.bounds[1])
    if (lo > hi).any():                                  # their boxes do not even meet
        return
    assert _clash(a, b) < 1.0, (pair, _clash(a, b))
    if tuple(sorted(pair)) in {tuple(sorted(t)) for t in TOUCHING}:
        assert _near(a, b) < 0.6, (pair, _near(a, b))    # and these two have to be in contact


# --- the panel's screws ---------------------------------------------------------------------
def _frame(deg):
    """Unit vectors along a meridian: out, round, up."""
    th = math.radians(deg)
    return (np.array([math.cos(th), math.sin(th), 0.0]),
            np.array([-math.sin(th), math.cos(th), 0.0]),
            np.array([0.0, 0.0, 1.0]))


def test_the_panels_screws_are_countersunk(sections):
    """Six at the skin, three point four two millimetres in: a real sink, not a cylinder.

    Read by asking the solid where its material is: a ring of points inside the hole must be
    outside the panel, and a ring just outside it must be in.
    """
    belly = sections["belly"]
    for z, deg in P.HATCH_SCREWS:
        out, tang, up = _frame(deg)
        # The skin at the sink's rim, found by four rays coming in from outside four millimetres
        # off the screw's line. Down the line itself there is a hole, and far enough away to
        # miss it the shoulder has already drawn in.
        centre = np.array([0.0, 0.0, z])
        rim = [centre + tang * s4 * 4.0 + up * u4 * 4.0 for s4, u4 in ((1, 0), (-1, 0), (0, 1), (0, -1))]
        hits = [belly.ray.intersects_location(np.array([o + out * 160.0]), np.array([-out]))[0] for o in rim]
        r_skin = float(np.median([max(math.hypot(*p[:2]) for p in h) for h in hits if len(h)]))
        assert r_skin > 0.0, (z, deg)
        for depth, hole, solid in ((0.3, 2.6, 3.4), (2.3, 1.2, 2.2)):
            centre = out * (r_skin - depth) + np.array([0.0, 0.0, z])
            ring = [centre + (tang * math.cos(a) + up * math.sin(a)) * rad
                    for rad in (hole, solid) for a in np.linspace(0.0, 2 * math.pi, 8, endpoint=False)]
            inside = belly.contains(np.array(ring))
            assert not inside[:8].any(), (z, deg, depth, "the hole is not open")
            # a majority, not all: the ring is at one radial depth on a curved panel, so its
            # far side is already outside the skin
            assert inside[8:].sum() >= 5, (z, deg, depth, "there is no material round the hole")


# --- the jet -----------------------------------------------------------------------------------
# How far down the jet may be aimed before the shell is in it. The axis leaves cleanly to -30,
# which is exactly the firmware fixture's own tiltMin; the Ø JET_D envelope wants five degrees
# more, because at -30 its lower edge passes about two millimetres inside the torso's neck rim,
# 46 mm out from the nozzle. Written down rather than rounded off: it is a real gap between what
# the machine may be commanded to do and what the shell allows.
AXIS_CLEAR_FROM = -30.0
RIM_CLEAR_FROM = -25.0


def _jet(deg):
    """Where the jet starts and which way it goes at this tilt, and a dozen rays round its rim.

    The machine's convention: positive is nose up, the same rotation `test_params` uses.
    """
    a = math.radians(deg)
    tip = np.array([math.sqrt(P.HEAD_R ** 2 - (P.Z_MOUTH - P.Z_HEAD) ** 2) + 1.0, 0.0, P.Z_MOUTH])
    dx, dz = tip[0], tip[2] - P.Z_HEAD
    start = np.array([dx * math.cos(a) - dz * math.sin(a), 0.0,
                      P.Z_HEAD + dx * math.sin(a) + dz * math.cos(a)])
    along = np.array([math.cos(a), 0.0, math.sin(a)])
    up = np.array([-math.sin(a), 0.0, math.cos(a)])
    side = np.array([0.0, 1.0, 0.0])
    rim = [start + (side * math.cos(t) + up * math.sin(t)) * (P.JET_D / 2)
           for t in np.linspace(0.0, 2 * math.pi, 12, endpoint=False)]
    return start, along, rim


def _hits(mesh, origins, direction):
    loc, idx, _ = mesh.ray.intersects_location(np.array(origins),
                                               np.tile(direction, (len(origins), 1)))
    if not len(loc):
        return None
    return float(np.linalg.norm(loc - np.array(origins)[idx], axis=1).min())


def test_the_jet_clears_the_shell(sections):
    """A JET_D column from the nozzle's tip, swung through the whole tilt range.

    Thirteen rays - the axis and a dozen round the rim - which is a sampling and not a proof:
    anything narrower than four millimetres could still slip between them. Nothing out there is.
    """
    for deg in np.arange(P.TILT_STOP[0], P.TILT_STOP[1] + 0.1, 5.0):
        start, along, rim = _jet(deg)
        for name in ("torso", "belly"):
            mesh = sections[name]
            if deg >= AXIS_CLEAR_FROM:
                d = _hits(mesh, [start], along)
                assert d is None, (f"the jet's axis hits {name} after {d:.0f} mm", deg)
            if deg >= RIM_CLEAR_FROM:
                d = _hits(mesh, rim, along)
                assert d is None, (f"the jet's edge hits {name} after {d:.0f} mm", deg)


# --- the head moves ------------------------------------------------------------------------------
def _fixed(sections, extras=True):
    others = {"torso": sections["torso"]}
    if extras:
        for name in EXTRA_MECH:
            path = STL / f"{name}.stl"
            assert path.exists(), f"EXTRA_MECH names {name}, which has not been built"
            others[name] = trimesh.load(path)
    return others


def _clash(moved, other):
    hit = trimesh.boolean.intersection([moved, other], engine=ENGINE)
    return volume_of(hit)


@pytest.mark.parametrize("deg", P.TILT_STOP)
def test_the_head_nods_to_its_stops(head_assembly, sections, deg):
    T = trimesh.transformations.rotation_matrix(math.radians(deg), (0.0, 1.0, 0.0), (0.0, 0.0, P.Z_HEAD))
    moved = head_assembly.copy().apply_transform(T)
    for name, other in _fixed(sections).items():
        assert _clash(moved, other) < 1.0, (deg, name)


@pytest.mark.parametrize("deg", (-P.PAN_STOP_DEG, P.PAN_STOP_DEG))
def test_the_head_pans_to_its_stops(head_assembly, sections, deg):
    T = trimesh.transformations.rotation_matrix(math.radians(deg), (0.0, 0.0, 1.0), (0.0, 0.0, 0.0))
    moved = head_assembly.copy().apply_transform(T)
    for name, other in _fixed(sections, extras=False).items():
        assert _clash(moved, other) < 1.0, (deg, name)


# --- the hat ------------------------------------------------------------------------------------
def test_the_hat_seats_on_the_head(sections):
    hat = sections["hat"]
    for name in ("head_back", "face"):
        assert _clash(hat, sections[name]) < 1.0, name
    # and it is a seat, not a hover: somewhere over the crown the felt comes within CLEAR of the
    # head. Not everywhere - the brim is hollow and the seat only cuts it where there is material
    pts = []
    for z in np.arange(P.Z_HAT, P.Z_HEAD + P.HEAD_R - 1.0, 1.0):
        ring = math.sqrt(max(P.HEAD_R ** 2 - (z - P.Z_HEAD) ** 2, 1.0))
        pts += [[ring * math.cos(a), ring * math.sin(a), z]
                for a in np.linspace(0.0, 2 * math.pi, 16, endpoint=False)]
    gap = trimesh.proximity.closest_point(hat, np.array(pts))[1]
    assert gap.min() < P.CLEAR + 0.2, gap.min()
