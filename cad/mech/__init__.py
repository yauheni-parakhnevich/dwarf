"""The mechanism. `ALL` is filled in by the part modules as they are written."""
from typing import Callable, NamedTuple

from build123d import Location


class Spec(NamedTuple):
    """A registered part: what builds it, and where that build sits in the machine."""
    name: str
    build: Callable
    placement: Location          # print frame -> assembled frame


ALL = []          # Spec, in build order
INTERFACES = {}   # shell section -> [part names unioned into it]


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
