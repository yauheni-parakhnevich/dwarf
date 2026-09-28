"""The mechanism. `ALL` is filled in by the part modules as they are written; `load_all()` imports
every one of them, so nothing that needs the whole registry has to name the modules itself."""
from typing import Callable, NamedTuple

from build123d import Location


class Spec(NamedTuple):
    """A registered part: what builds it, and where that build sits in the machine."""
    name: str
    build: Callable
    placement: Location          # print frame -> assembled frame


ALL = []          # Spec, in build order
INTERFACES = {}   # shell section -> [part names unioned into it]
MODULES = ("mech.turntable", "mech.nod", "mech.collar", "mech.head", "mech.filler", "mech.torso", "mech.base")

# What moves, and how. The head pans about Z and nods about Y, both about C = (0, 0, Z_NOD).
# PANS: turns with the plate and does not nod - the plate with its hub, its cheeks and the nod
# servo's posts, and the ring that clamps the bearing's inner ring to it. NODS: pans and nods -
# the stem, the spider on it, and (unioned into the head) the nozzle holder; with them the shell's
# beard, head and hat. The pan linkage moves too, but on its own axes: crank_pins() places it.
PANS = ("plate", "hub_ring", "servo_shim", "tube_clip")
NODS = ("stem", "spider", "nozzle_holder")
SHELL_NODS = ("beard_left", "beard_right", "head", "hat")
LINKAGE = ("servo_crank", "pan_link")


def load_all():
    """Import every part module, which is what registers the parts."""
    import importlib
    for m in MODULES:
        importlib.import_module(m)
    return ALL


def part(name, section=None, placement=None):
    """Register a builder.

    A builder returns its part in the frame it is printed in. `placement` says where that
    frame lands in the assembled machine, and only `assembly()` ever applies it - the STEP and
    STL a printer is given are the print frame. Most parts are drawn where they sit and so
    declare nothing. Interface parts also name the shell section they join.
    """
    def wrap(fn):
        ALL.append(Spec(name, fn, placement or Location()))
        if section:
            INTERFACES.setdefault(section, []).append(name)
        return fn
    return wrap
