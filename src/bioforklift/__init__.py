from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("bioforklift")
except PackageNotFoundError:
    # Package is not installed (e.g. running from a source checkout)
    __version__ = "unknown"
