"""
Packaged prompts for the retrieval stack.

Loaded via :func:`importlib.resources.files` so wheel installs from
PyPI find the same prompt the editable install does. PHX-0049 (Hesiod
Option A): keeping prompts inside the package directory is the
standard idiom for shipping data files with a Python distribution
and removes the install-layout-fragile ``parents[3]`` path computation
the original E8 loader used.

This module is intentionally empty — its existence makes the
directory a package, which is the requirement for
``importlib.resources.files("theogony.retrieval.prompts")`` to
succeed across all Python install layouts.
"""
