"""Cloud/SaaS support for mac-digital-human.

The local Apple-Silicon application remains the default entrypoint. Modules in
this package add cloud configuration, queueing, storage and API surfaces
without forcing the desktop workflow to depend on SaaS infrastructure.
"""

from .settings import SaaSSettings, saas_settings

__all__ = ["SaaSSettings", "saas_settings"]
