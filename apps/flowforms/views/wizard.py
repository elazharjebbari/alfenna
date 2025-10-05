from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, Optional, Iterable, Tuple

from django import forms
from django.http import HttpResponseBadRequest, HttpResponse, HttpRequest
from django.shortcuts import render, redirect
from django.urls import reverse
from formtools.wizard.views import SessionWizardView

from apps.flowforms.conf.loader import get_flow
from apps.flowforms.engine.forms_builder import build_form_for_step
from apps.flowforms.engine.router import Router, FINISH
from apps.flowforms.engine.storage import FlowContext, get_or_create_session, persist_step
from apps.flowforms.models import FlowStatus
from apps.leads.models import Lead
from apps.leads.submissions import submit_lead_from_flowsession



@dataclass
class _PostedCTA:
    next_step: Optional[str] = None


class FlowFormsWizardView(SessionWizardView):
    """
    Wizard multi-étapes piloté par YAML + Router + FlowSession.
    Défensif vis-à-vis de formtools : toujours fournir un form_list valide.
    """

    template_name = "flowforms/wizard_form.html"

    # Placeholder sûr au niveau classe (utilisé par formtools à import-time)
    # NB: on met une liste de tuples pour passer par le chemin le plus robuste
    form_list = [("_bootstrap", forms.Form)]

    # --------- durcissement formtools (import-time) ---------
    @classmethod
    def get_initkwargs(cls, *args, **kwargs):
        """
        Garanti que formtools reçoit *toujours* un form_list constitué de classes.
        Remplace toute valeur None/mauvaise par forms.Form.
        Accepte dict, liste de tuples, ou tuple.
        """
        raw = kwargs.get("form_list", None)
        if not raw:
            raw = getattr(cls, "form_list", None)

        normalized: Iterable[Tuple[str, type]] = []

        if isinstance(raw, dict):
            items = list(raw.items())
        elif isinstance(raw, (list, tuple)):
            items = list(raw)
        else:
            items = [("_bootstrap", forms.Form)]

        fixed: list[Tuple[str, type]] = []
        for key, val in items:
            # si la valeur n'est pas une *classe*, on substitue forms.Form
            if not isinstance(val, type):
                val = forms.Form
            fixed.append((str(key), val))

        kwargs["form_list"] = fixed
        return super().get_initkwargs(*args, **kwargs)

    # --------- runtime helpers ---------
    def _decode_action(self, request: HttpRequest) -> tuple[str, Optional[str]]:
        raw = request.POST.get("flowforms_action", "next::")
        if "::" in raw:
            act, nxt = raw.split("::", 1)
            return (act or "next"), (nxt or None)
        return (raw or "next"), None

    def _load_runtime(self, request: HttpRequest, *, flow_key: str):
        self.flow_cfg: Dict[str, Any] = get_flow(flow_key)  # dict
        self.ctx = FlowContext(flow_key=flow_key, form_kind=self.flow_cfg["kind"])
        self.fs = get_or_create_session(request, self.ctx)
        self.router = Router.from_flow(self.flow_cfg)
        self.snapshot: Dict[str, Any] = self.fs.data_snapshot or {}

    def _current_key(self) -> str:
        cur = self.fs.current_step or ""
        if not cur:
            return self.router.first_visible_step_key(self.snapshot)
        visible = [s.key for s in self.router.visible_steps(self.snapshot)]
        if cur not in visible and cur != FINISH:
            return self.router.first_visible_step_key(self.snapshot)
        return cur

    # --------- API formtools (runtime) ---------
    def get_form_list(self) -> "OrderedDict[str, type[forms.Form]]":
        """
        Renvoie la liste des steps (placeholders) une fois la conf chargée.
        Si appelée trop tôt (avant _load_runtime), renvoie un placeholder sûr.
        """
        if not hasattr(self, "flow_cfg"):
            return OrderedDict([("_bootstrap", forms.Form)])

        steps = OrderedDict()
        for s in (self.flow_cfg.get("steps") or []):
            steps[s["key"]] = forms.Form  # placeholder; le vrai form est construit dans get_form()
        return steps

    def get_form(self, step=None, data=None, files=None):
        step_key = step or self._current_key()
        step_cfg = next(s for s in self.flow_cfg["steps"] if s["key"] == step_key)
        lead = self.fs.lead or Lead(form_kind=self.flow_cfg["kind"])

        unbound = build_form_for_step(step_cfg, instance=lead)
        FormClass = unbound.__class__
        if data is None and files is None:
            return unbound
        return FormClass(data=data, files=files, instance=lead)

    def get_template_names(self):
        return [self.template_name]

    def get_context_data(self, form, **kwargs):
        step_key = self._current_key()
        step_cfg = next(s for s in self.flow_cfg["steps"] if s["key"] == step_key)
        visibles = [s.key for s in self.router.visible_steps(self.snapshot)]
        idx = (visibles.index(step_key) + 1) if step_key in visibles else 1
        total = max(len(visibles), 1)

        ctx = super().get_context_data(form=form, **kwargs)
        ctx.update({
            "flow": self.flow_cfg,
            "step": step_cfg,
            "flowsession": self.fs,
            "progress": {"index": idx, "total": total},
        })
        return ctx

    # --------- HTTP ---------
    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        flow_key = kwargs.get("flow_key")
        try:
            self._load_runtime(request, flow_key=flow_key)
        except KeyError:
            return HttpResponseBadRequest(f"Flow '{flow_key}' not found in configuration.")

        step_key = self._current_key()
        if step_key == FINISH:
            return self._render_done()

        form = self.get_form(step=step_key)
        return render(request, self.template_name, self.get_context_data(form=form))

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        flow_key = kwargs.get("flow_key")
        try:
            self._load_runtime(request, flow_key=flow_key)
        except KeyError:
            return HttpResponseBadRequest(f"Flow '{flow_key}' not found in configuration.")

        action, jump_to = self._decode_action(request)
        posted_cta = _PostedCTA(next_step=jump_to)

        current_key = self._current_key()
        if current_key == FINISH:
            return self._render_done()

        form = self.get_form(step=current_key, data=request.POST or None, files=request.FILES or None)
        if not form.is_valid():
            return render(request, self.template_name, self.get_context_data(form=form))

        lead, self.fs = persist_step(
            flowsession=self.fs,
            ctx=self.ctx,
            step_key=current_key,
            cleaned_data=form.cleaned_data,
        )
        self.snapshot = self.fs.data_snapshot or {}

        next_key = self.router.resolve(
            current_key=current_key, action=action, snapshot=self.snapshot, posted_cta=posted_cta,
        )
        if next_key == FINISH:
            return self._mark_completed_and_render_done()

        self.fs.current_step = next_key
        self.fs.save(update_fields=["current_step", "updated_at"])
        return redirect(reverse("flowforms:wizard", kwargs={"flow_key": self.ctx.flow_key}))

    # --------- done ---------
    def _render_done(self) -> HttpResponse:
        return render(self.request, "flowforms/done.html", {
            "flow": self.flow_cfg,
            "lead": self.fs.lead,
            "flowsession": self.fs,
        })

    def _mark_completed_and_render_done(self) -> HttpResponse:
        # 1) Soumission vers leads (idempotente)
        try:
            submit_lead_from_flowsession(self.fs)
        except Exception:
            # Pas d'exception remontée à l'utilisateur
            pass

        # 2) Marquer complété côté FlowForms
        if self.fs.status != FlowStatus.COMPLETED:
            self.fs.status = FlowStatus.COMPLETED
            self.fs.save(update_fields=["status", "updated_at"])
        return self._render_done()