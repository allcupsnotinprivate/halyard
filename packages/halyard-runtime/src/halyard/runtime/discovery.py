"""Package autodiscovery: import modules so their decorators fire.

Registration stays explicit (the ``@component`` decorator on the class);
autodiscovery only removes the manual "import every module" list. Private
modules (leading underscore) are skipped.
"""

from importlib import import_module
import pkgutil


def autodiscover(*packages: str) -> tuple[str, ...]:
    """Import every module of the given packages; return the imported names."""
    imported: list[str] = []
    for name in packages:
        package = import_module(name)
        imported.append(name)
        path = getattr(package, "__path__", None)
        if path is None:
            continue  # a plain module, nothing more to walk
        for info in pkgutil.walk_packages(path, prefix=f"{name}."):
            if info.name.rsplit(".", 1)[-1].startswith("_"):
                continue
            import_module(info.name)
            imported.append(info.name)
    return tuple(imported)
