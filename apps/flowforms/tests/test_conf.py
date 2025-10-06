# apps/flowforms/tests/test_conf.py (extrait)
from django.test import TestCase, override_settings
from django.core.exceptions import ValidationError
from pathlib import Path
import tempfile
import yaml

from apps.flowforms.conf.loader import load_config, invalidate_config_cache

class FlowFormsConfigTests(TestCase):
    def test_config_invalid_op_fails(self):
        bad = {
            "flows": {
                "x": {
                    "key": "x",
                    "steps": [
                        {
                            "key": "s1",
                            "fields": [],
                            "transitions": [
                                {"when": {"op": "doesnotexist", "left": "a", "right": 1}, "to": "s2"}
                            ],
                        }
                    ],
                }
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.yaml"
            p.write_text(yaml.safe_dump(bad), encoding="utf-8")

            with override_settings(FLOWFORMS_POLICY_YAML=str(p)):
                # Très important : on invalide le cache AVANT le load
                invalidate_config_cache()
                with self.assertRaises(ValidationError):
                    load_config(reload=False)  # le mtime diffère; on pourrait aussi mettre reload=True