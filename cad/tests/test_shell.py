"""What the assembled shell has to be true of. Skipped until `build.py assemble` has run.

These are slow by the standards of the rest of the suite - a few of them run manifold booleans
on a third of a million triangles - so the meshes are loaded once per session and the derived
ones are cached too.
"""
import math
from pathlib import Path

import numpy as np
import pytest
import trimesh

import params as P
from mech import INTERFACES

STL = Path(__file__).resolve().parents[1] / "out" / "stl"
SECTIONS = ("base", "torso", "belly", "beard", "head_back", "face", "hat")
HEAD = ("head_back", "face", "hat")
ENGINE = "manifold"

# Mech parts that share the head's swept space and want checking against it. The turntable's
# neck_shroud is being drawn now; add "neck_shroud" here when its STL exists and the nod and pan
# tests will take it into account without any other change.
EXTRA_MECH: tuple = ()

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


def test_the_collar_screws_pass_the_torso_into_the_beard(sections):
    """Three M3s from inside the torso, through its wall, into inserts in the collar."""
    z = P.Z_TORSO_TOP - 4.0
    for deg in (90.0, 210.0, 330.0):
        th = math.radians(deg)
        d = (math.cos(th), math.sin(th), 0.0)
        assert _flies(sections["torso"], (0.0, 0.0, z), d, P.shell_r(P.TORSO_PROFILE, z) + 5.0), deg
        # down the bore, and again beside it: the difference is how deep the insert can go
        bore = _first_radius(sections["beard"], z, d)
        face = _first_radius(sections["beard"], z + 7.0, d)
        assert bore is not None and face is not None, deg
        assert bore - face >= P.INSERT_DEPTH - 0.5, (deg, bore, face)


# --- the interface parts --------------------------------------------------------------------------
def test_every_interface_part_was_taken_into_its_section(sections):
    """Nothing of a part may stand outside the section it was unioned into."""
    for section, names in INTERFACES.items():
        for name in names:
            part = trimesh.load(STL / f"{name}.stl")
            left = trimesh.boolean.difference([part, sections[section]], engine=ENGINE)
            # the ear boss keeps a sliver: the assembler drills its M4 bore after the union, which
            # takes away the corner of the stop tab that ear_boss itself leaves in the bore
            assert volume_of(left) < 0.01 * part.volume, (section, name, volume_of(left), part.volume)


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


# --- the head moves ------------------------------------------------------------------------------
def _fixed(sections):
    others = {"beard": sections["beard"], "torso": sections["torso"]}
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
    for name, other in _fixed(sections).items():
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
