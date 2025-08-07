__all__ = []

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    __version__ = "0.0.0"

# convenience entry-point

def main() -> None:  # pragma: no cover
    """Run the demo server (python -m genai_server)."""
    from . import server  # noqa: WPS433 (import inside function)

    if hasattr(server, 'main'):
        server.main()
