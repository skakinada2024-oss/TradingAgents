"""Local Paper Trading Terminal. Simulation UI only."""

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    from .server import main as serve

    return serve(argv)
