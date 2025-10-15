__all__ = ["StringTranslation", "TranslatableMixin", "build_translation_key", "model_identifier"]


def __getattr__(name):
    if name == "StringTranslation":
        from .models import StringTranslation

        return StringTranslation
    if name == "TranslatableMixin":
        from .models import TranslatableMixin

        return TranslatableMixin
    if name == "build_translation_key":
        from .utils import build_translation_key

        return build_translation_key
    if name == "model_identifier":
        from .utils import model_identifier

        return model_identifier
    raise AttributeError(f"module 'apps.i18n' has no attribute '{name}'")
