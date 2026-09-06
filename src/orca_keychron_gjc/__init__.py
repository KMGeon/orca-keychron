"""GJC bridge integration for the Orca Keychron display."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("orca-keychron")
except PackageNotFoundError:
    __version__ = "0.1.0"
