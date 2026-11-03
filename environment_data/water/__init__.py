"""Water risk data connectors.

    AqueductClient  -- baseline + projected water stress (WRI Aqueduct 4.0, no auth)
"""

from .aqueduct import AqueductClient

__all__ = ["AqueductClient"]
