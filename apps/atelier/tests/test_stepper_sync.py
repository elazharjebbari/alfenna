from __future__ import annotations

import json
import re
import subprocess
import textwrap
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class LeadStepperSyncTests(SimpleTestCase):
    def _extract_stepper_script(self) -> str:
        template_path = (
            Path(settings.BASE_DIR)
            / "templates"
            / "components"
            / "core"
            / "forms"
            / "lead_step3"
            / "lead_step3.html"
        )
        html = template_path.read_text(encoding="utf-8")
        match = re.search(r"<script>\s*(\(function[\s\S]+?)</script>", html)
        self.assertIsNotNone(match, "Stepper synchronisation script not found")
        return match.group(1)

    def test_stepper_active_state_tracks_visible_form_step(self) -> None:
        script_content = self._extract_stepper_script()
        node_snippet = textwrap.dedent(
            f"""
            const scriptContent = {json.dumps(script_content)};

            class ClassList {{
                constructor(initial) {{ this.items = new Set(initial || []); }}
                add(name) {{ this.items.add(name); }}
                remove(name) {{ this.items.delete(name); }}
                delete(name) {{ this.items.delete(name); }}
                toggle(name, force) {{
                    const shouldAdd = force === undefined ? !this.items.has(name) : !!force;
                    if (shouldAdd) {{
                        this.items.add(name);
                    }} else {{
                        this.items.delete(name);
                    }}
                }}
                contains(name) {{ return this.items.has(name); }}
            }}

            class StepElement {{
                constructor(hidden) {{
                    this.classList = new ClassList(hidden ? ['d-none'] : []);
                    this._observers = [];
                }}
                setHidden(hidden) {{
                    this.classList.toggle('d-none', hidden);
                    this._observers.forEach((cb) => cb());
                }}
            }}

            class PillElement {{
                constructor(active = false) {{
                    this.classList = new ClassList(active ? ['is-active'] : []);
                }}
            }}

            const stepElements = [
                new StepElement(false),
                new StepElement(true),
                new StepElement(true),
                new StepElement(true),
            ];
            const pillElements = [
                new PillElement(true),
                new PillElement(false),
                new PillElement(false),
                new PillElement(false),
            ];

            const root = {{
                querySelectorAll(selector) {{
                    if (selector === '[data-ff-step]') return stepElements;
                    return [];
                }},
                addEventListener(event, handler) {{
                    if (event === 'click') this._clickHandler = handler;
                }},
                triggerClick(target) {{
                    if (this._clickHandler) this._clickHandler({{ target }});
                }},
            }};

            const document = {{
                querySelector(selector) {{
                    if (selector === '[data-ff-root]') return root;
                    return null;
                }},
                querySelectorAll(selector) {{
                    if (selector === '.af-stepper .af-pill') return pillElements;
                    return [];
                }},
            }};

            global.document = document;
            global.MutationObserver = class {{
                constructor(callback) {{ this._callback = callback; }}
                observe(step) {{
                    step._observers.push(() => this._callback());
                }}
            }};
            global.setTimeout = (fn) => fn();

            eval(scriptContent);

            const toStates = () => pillElements.map((pill) => pill.classList.contains('is-active'));

            const initial = toStates();

            stepElements[0].setHidden(true);
            stepElements[1].setHidden(false);
            const afterSecond = toStates();

            stepElements[1].setHidden(true);
            stepElements[2].setHidden(false);
            const afterThird = toStates();

            console.log(JSON.stringify({{ initial, afterSecond, afterThird }}));
            """
        )

        completed = subprocess.run(
            ["node", "-e", node_snippet],
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(completed.stdout.strip())
        self.assertEqual(payload["initial"], [True, False, False, False])
        self.assertEqual(payload["afterSecond"], [False, True, False, False])
        self.assertEqual(payload["afterThird"], [False, False, True, False])
