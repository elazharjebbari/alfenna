# apps/flowforms/views.py
from __future__ import annotations
from django.shortcuts import render, redirect
from django.views import View
from django.http import JsonResponse, HttpResponseBadRequest
from django.template.loader import render_to_string

from apps.flowforms.conf.loader import load_config, get_flow
from apps.flowforms.engine.forms_builder import build_form_for_step
from apps.flowforms.engine.router import Router, FINISH
from apps.flowforms.engine.storage import get_or_create_session, persist_step, FlowContext
from apps.leads.models import Lead

class HealthCheckView(View):
    def get(self, request, *args, **kwargs):
        return JsonResponse({"ok": True, "app": "flowforms"}, status=200)

class FlowWizardView(View):
    """
    Wizard minimal piloté par la config :
    - GET : calcule la step visible courante et affiche le form
    - POST : valide, persiste, route selon l’action (prev/next/jump/submit)
    """
    template_name = "flowforms/wizard.html"

    def _decode_action(self, request):
        raw = request.POST.get("flowforms_action", "next::")
        if "::" in raw:
            act, next_step = raw.split("::", 1)
            return act or "next", next_step or None
        return raw or "next", None

    def get(self, request, flow_key, *args, **kwargs):
        try:
            flow_cfg = get_flow(flow_key)
        except KeyError:
            # Flow inconnu => 404 claire (meilleure DX que 500)
            return HttpResponseBadRequest(f"Flow '{flow_key}' not found in configuration.")

        ctx = FlowContext(
            flow_key=flow_key,
            form_kind=flow_cfg["kind"],
            lookup_fields=("email", "phone"),
        )
        fs = get_or_create_session(request, ctx)
        router = Router.from_flow(flow_cfg)
        snapshot = fs.data_snapshot or {}

        current_key = fs.current_step or ""
        try:
            step_key = current_key or router.first_visible_step_key(snapshot)
        except KeyError:
            step_key = router.first_visible_step_key(snapshot)

        if step_key == FINISH:
            return render(request, "flowforms/done.html", {"flow": flow_cfg, "lead": fs.lead, "flowsession": fs})

        # step_key a déjà été calculé juste au-dessus
        if step_key == FINISH:
            return render(request, "flowforms/done.html", {"flow": flow_cfg, "lead": fs.lead, "flowsession": fs})

        # Récupère la config de step de façon sûre
        steps_list = flow_cfg.get("steps") or []
        step_cfg = next((s for s in steps_list if s.get("key") == step_key), None)
        if step_cfg is None:
            # Si la step courante n'existe pas (changement de conf), se rabat sur la 1re visible
            fallback_key = router.first_visible_step_key(snapshot)
            if fallback_key == FINISH:
                return render(request, "flowforms/done.html", {"flow": flow_cfg, "lead": fs.lead, "flowsession": fs})
            step_cfg = next(s for s in steps_list if s.get("key") == fallback_key)
            step_key = fallback_key

        lead = fs.lead or Lead(form_kind=flow_cfg["kind"])
        form = build_form_for_step(step_cfg, instance=lead)

        return render(request, self.template_name, {
            "flow": flow_cfg, "step": step_cfg, "form": form, "flowsession": fs,
        })

    def post(self, request, flow_key, *args, **kwargs):
        act, jump_target = self._decode_action(request)
        try:
            flow_cfg = get_flow(flow_key)
        except KeyError:
            return HttpResponseBadRequest(f"Flow '{flow_key}' not found in configuration.")

        ctx = FlowContext(
            flow_key=flow_key,
            form_kind=flow_cfg["kind"],
            lookup_fields=("email", "phone"),
        )
        fs = get_or_create_session(request, ctx)
        router = Router.from_flow(flow_cfg)

        snapshot = fs.data_snapshot or {}
        current_key = fs.current_step or router.first_visible_step_key(snapshot)
        if current_key == FINISH:
            return render(request, "flowforms/done.html", {"flow": flow_cfg, "lead": fs.lead, "flowsession": fs})

        steps_list = flow_cfg.get("steps") or []
        step_cfg = next(s for s in steps_list if s.get("key") == current_key)
        lead = fs.lead or Lead(form_kind=flow_cfg["kind"])
