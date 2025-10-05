from __future__ import annotations

from django.contrib.staticfiles.management.commands.runserver import Command as StaticfilesRunserverCommand


class Command(StaticfilesRunserverCommand):
    """Default to WhiteNoise for serving static assets in development."""

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.set_defaults(use_static_handler=False)
