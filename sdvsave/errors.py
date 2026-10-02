"""Errors raised by the save logic, free of any display language.

The logic doesn't know which language the UI is shown in. An error therefore
carries a translation key and its parameters; the UI turns it into a sentence
in the chosen language.
"""


class T(str):
    """A parameter that is itself a key to translate (for example a field name)."""


class SaveError(ValueError):
    def __init__(self, key, **params):
        super().__init__(key)
        self.key = key
        self.params = params


class NotFound(SaveError, KeyError):
    """Player, backup or XML tag not found."""


class SaveChangedError(SaveError):
    """The file changed on disk (because of the game?) since it was loaded."""

    def __init__(self):
        super().__init__("error.save_changed")