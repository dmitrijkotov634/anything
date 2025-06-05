from typing import Callable

from anything import LazyAnything

lazy = LazyAnything(env=globals())


# noinspection PyUnusedLocal
@lazy.register
def max_(a: int, b: int) -> int:
    """Return max number"""


# noinspection PyUnusedLocal
@lazy.register
def randint_generator(
        count: int = 5,
        min_int: int = 0,
        max_int: int = 10
) -> list[int]:
    """Return random numbers"""


# noinspection PyUnusedLocal
@lazy.register
def run_with_analyze(func: Callable) -> None:
    """Analyze RAM usage and runtime"""


# noinspection PyUnusedLocal
@lazy.register
def main() -> None:
    """Generate 10 random numbers from 10 to 100 and output after finding the maximum using max_"""


run_with_analyze(main)
