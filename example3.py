from anything import LazyAnything

lazy = LazyAnything(env=globals())


# noinspection PyUnusedLocal
@lazy.register
def calculator(exp: str) -> int:
    """Return calculation! VERY SAFE"""


print(calculator("1+1"))
