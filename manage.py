#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def _using_dev_settings(argv: list[str]) -> bool:
    """Return True if runserver targets the dev settings module."""
    for idx, arg in enumerate(argv):
        if arg == "--settings" and idx + 1 < len(argv):
            return argv[idx + 1].endswith(".dev")
    module = os.environ.get("DJANGO_SETTINGS_MODULE", "") or ""
    if module:
        return module.endswith(".dev")
    return True  # default manage.py points to alfenna.settings → alias to dev


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'alfenna.settings.dev')

    if len(sys.argv) >= 2 and sys.argv[1] == 'runserver' and '--nostatic' not in sys.argv:
        if _using_dev_settings(sys.argv):
            sys.argv.insert(2, '--nostatic')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
