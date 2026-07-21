"""NESTfetch site adapters package.

Each supported download site is implemented as a `SiteAdapter` subclass in its
own module here. The engine stays completely site-agnostic and is driven by
whichever adapter is selected at runtime (see `sites.registry`).
"""
