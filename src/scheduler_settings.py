import sys

from console_util import read_line


def required(settings, section, name):
    if section in settings and name in settings[section]:
        return _typed_return(settings[section][name])
    read_line("Missing setting " + name + " in section " + section + "! Press enter to quit. ")
    sys.exit(0)


def optional(settings, section, name, default_value):
    if section in settings and name in settings[section]:
        return _typed_return(settings[section][name])
    shown = str(default_value).lower() if isinstance(default_value, bool) else str(default_value)
    print("Defaulting setting " + name + " in section " + section + " to " + shown + ".")
    return default_value


def _typed_return(prop):
    """
    Same order as the original: try int, then float (which overrides the int, so
    numbers come back as float), then boolean. Anything else stays a string.
    """
    if not isinstance(prop, str):
        return prop
    return_value = prop
    try:
        return_value = int(prop)
    except ValueError:
        pass
    try:
        return_value = float(prop)
    except ValueError:
        pass
    if prop.lower() in ("true", "false"):
        return_value = prop.lower() == "true"
    return return_value


# --- Typed helpers for callers (Groovy coerced these implicitly) ---

def as_int(o):
    if isinstance(o, (int, float)):
        return int(o)
    return int(str(o).strip())


def as_boolean(o):
    """Groovy truthiness for a setting value."""
    return bool(o)
