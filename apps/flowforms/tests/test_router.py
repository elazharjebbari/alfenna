from __future__ import annotations
from django.test import TestCase, RequestFactory
from django.contrib.sessions.middleware import SessionMiddleware

from apps.flowforms.engine.router import Router, FINISH
from apps.flowforms.engine.storage import FlowContext, get_or_create_session, persist_step
from apps.leads.models import Lead

def add_session(request):
    mw = SessionMiddleware(lambda r: None)
    mw.process_request(request)
    request.session.save()
    return request

class FlowFormsRouterTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.flow_cfg = {
            "key": "demo_flow",
            "kind": "checkout_intent",
            "steps": [
                {
                    "key": "s1",
                    "title": "Step 1",
                    "fields": [{"name": "email", "type": "email", "required": True}],
                    "ctas": [{"action": "next", "label": "Continuer"}],
                },
                {
                    "key": "s2",
                    "title": "Step 2 (conditional)",
                    "show_if": [{"field": "context.skip_s2", "op": "is_false"}],
                    "fields": [{"name": "context.extra", "type": "text"}],
                    "ctas": [{"action": "next", "label": "Suivant"}],
                },
                {
                    "key": "s3",
                    "title": "Step 3",
                    "fields": [{"name": "phone", "type": "phone"}],
                    "ctas": [
                        {"action": "prev", "label": "Retour"},
                        {"action": "jump", "label": "Aller à S1", "next_step": "s1"},
                        {"action": "submit", "label": "Envoyer"},
                    ],
                    "conditions": [
                        # si phone == "000", fin anticipée (via transition)
                        {"field": "phone", "op": "equals", "value": "000", "next": "__FINISH__"},
                    ],
                },
            ],
        }

    def test_conditionally_hidden_step_is_skipped(self):
        router = Router.from_flow(self.flow_cfg)
        snapshot = {"email": "a@b.com", "context": {"skip_s2": True}}  # s2 doit être masquée
        first_key = router.first_visible_step_key(snapshot)
        self.assertEqual(first_key, "s1")

        # next depuis s1 doit aller directement à s3 (s2 masquée)
        nxt = router.resolve(current_key="s1", action="next", snapshot=snapshot)
        self.assertEqual(nxt, "s3")

    def test_cta_jump_to_specific_step(self):
        router = Router.from_flow(self.flow_cfg)
        snapshot = {"email": "x@y.com", "context": {"skip_s2": False}}  # s2 visible
        # Depuis s3, un jump vers s1
        class _CTA:  # helper
            def __init__(self, next_step): self.next_step = next_step
        nxt = router.resolve(current_key="s3", action="jump", snapshot=snapshot, posted_cta=_CTA("s1"))
        self.assertEqual(nxt, "s1")

    def test_prev_keeps_data_intact(self):
        """
        On valide s1, on passe à s2 (visible), on clique prev depuis s2 => retour s1 sans perte des données.
        """
        router = Router.from_flow(self.flow_cfg)
        ctx = FlowContext(flow_key="demo_flow", form_kind="checkout_intent")

        req = add_session(self.factory.get("/flows/demo_flow/"))
        fs = get_or_create_session(req, ctx)

        # persist s1
        lead, fs = persist_step(flowsession=fs, ctx=ctx, step_key="s1",
                                cleaned_data={"email": "keep@data.com"})
        snapshot = fs.data_snapshot
        self.assertEqual(snapshot.get("email"), "keep@data.com")

        # déterminer next (s2 est visible car skip_s2=False par défaut)
        nxt = router.resolve(current_key="s1", action="next", snapshot=snapshot)
        self.assertEqual(nxt, "s2")

        # prev depuis s2 => s1, snapshot inchangé
        prev = router.resolve(current_key="s2", action="prev", snapshot=snapshot)
        self.assertEqual(prev, "s1")
        self.assertEqual(fs.data_snapshot.get("email"), "keep@data.com")