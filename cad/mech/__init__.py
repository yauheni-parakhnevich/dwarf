"""The mechanism. `ALL` is filled in by the part modules as they are written."""
ALL = []          # (name, builder) in build order
INTERFACES = {}   # shell section -> [part names unioned into it]


def part(name, section=None):
    """Register a builder. Interface parts also name the shell section they join."""
    def wrap(fn):
        ALL.append((name, fn))
        if section:
            INTERFACES.setdefault(section, []).append(name)
        return fn
    return wrap
