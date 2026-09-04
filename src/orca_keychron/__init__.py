"""Orca agent status indicator for Keychron keyboards."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("orca-keychron")
except PackageNotFoundError:
    __version__ = "0.1.0"
