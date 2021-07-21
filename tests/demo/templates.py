__all__ = ('templates',)

from foxglove import glove
from foxglove.templates import FoxgloveTestTemplates, FoxgloveTemplates

if glove.settings.test_mode:
    templates = FoxgloveTestTemplates()
else:
    templates = FoxgloveTemplates()
