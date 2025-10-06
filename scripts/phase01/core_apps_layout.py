# scripts/core_apps_layout.py
from django.conf import settings
import importlib

def run(*args):
    print("== core_apps_layout: début ==")

    required_apps = [
        'django.contrib.admin',
        'django.contrib.auth',
        'django.contrib.contenttypes',
        'django.contrib.sessions',
        'django.contrib.messages',
        'django.contrib.staticfiles',
        'widget_tweaks',
        'OnlineLearning.apps.OnlinelearningConfig',
    ]
    missing = [a for a in required_apps if a not in settings.INSTALLED_APPS]
    assert not missing, f"Apps manquantes: {missing}"

    # Import smoke
    for mod in ['OnlineLearning', 'OnlineLearning.models', 'OnlineLearning.views']:
        importlib.import_module(mod)

    # Templates dirs
    dirs = settings.TEMPLATES[0]['DIRS']
    assert any(str(p).endswith('/templates') for p in dirs), "Répertoire 'templates' non référencé"

    # Lang/TZ
    assert settings.LANGUAGE_CODE == 'fr-fr', "LANGUAGE_CODE inattendu"
    assert settings.TIME_ZONE == 'Africa/Casablanca', "TIME_ZONE inattendu"

    print("== core_apps_layout: OK ✅ ==")
