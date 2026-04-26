"""Service package namespace.

Keep this initializer side-effect free. Temporal activities import individual
service submodules during worker startup, and eager convenience exports here
can create cycles through the workflow modules.
"""

__all__: list[str] = []
