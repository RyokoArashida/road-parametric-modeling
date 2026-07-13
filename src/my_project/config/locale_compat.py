# ruff: noqa: E402
import locale


def normalize_lc_time() -> None:
    """Avoid RhinoCode returning Windows locale names that Python cannot parse."""
    try:
        locale.getlocale(locale.LC_TIME)
    except ValueError:
        locale.setlocale(locale.LC_TIME, "C")
