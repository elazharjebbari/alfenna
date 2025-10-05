# apps/flowforms/engine/router.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

from .steps import Step, CTA

FINISH = "__FINISH__"  # marqueur spécial pour fin anticipée ou submit final

@dataclass
class Router:
    flow_cfg: Dict[str, Any]  # dict validé par schéma (FlowConfig)
    steps: List[Step]

    @classmethod
    def from_flow(cls, flow_cfg: Dict[str, Any]) -> "Router":
        steps = [Step.from_config(s) for s in (flow_cfg.get("steps") or [])]
        return cls(flow_cfg=flow_cfg, steps=steps)

    # ---------- visibilité ----------
    def is_step_visible(self, step: Step, snapshot: Dict[str, Any]) -> bool:
        if not step.show_if:
            return True
        return all(cond.evaluate(snapshot) for cond in step.show_if)

    def visible_steps(self, snapshot: Dict[str, Any]) -> List[Step]:
        return [s for s in self.steps if self.is_step_visible(s, snapshot)]

    # ---------- helpers ----------
    def get_step(self, key: str) -> Step:
        for s in self.steps:
            if s.key == key:
                return s
        raise KeyError(f"Step '{key}' not found")

    def first_visible_step_key(self, snapshot: Dict[str, Any]) -> str:
        vs = self.visible_steps(snapshot)
        if not vs:
            # s’il n’y a aucune step visible, on considère le flow comme terminé
            return FINISH
        return vs[0].key

    def prev_visible_step_key(self, current_key: str, snapshot: Dict[str, Any]) -> Optional[str]:
        vs = self.visible_steps(snapshot)
        keys = [s.key for s in vs]
        if current_key not in keys:
            # si la step actuelle n'est plus visible, se rabat sur la première visible
            return self.first_visible_step_key(snapshot)
        idx = keys.index(current_key)
        return keys[idx - 1] if idx > 0 else None

    def next_visible_step_key(self, current_key: str, snapshot: Dict[str, Any]) -> Optional[str]:
        vs = self.visible_steps(snapshot)
        keys = [s.key for s in vs]
        if current_key not in keys:
            return self.first_visible_step_key(snapshot)
        idx = keys.index(current_key)
        return keys[idx + 1] if idx < len(keys) - 1 else None

    # ---------- transitions de step ----------
    def _apply_step_transitions(self, step: Step, snapshot: Dict[str, Any]) -> Optional[str]:
        """
        Si la step possède des transitions conditionnelles (conditions[].next),
        renvoie la prochaine clé si l'une matche. Sinon None.
        """
        for cond in step.transitions:
            if cond.evaluate(snapshot):
                return cond.next or None
        return None

    # ---------- décision principale ----------
    def resolve(self, *, current_key: str, action: str, snapshot: Dict[str, Any], posted_cta: Optional[CTA] = None) -> str:
        """
        Renvoie la prochaine clé de step (ou FINISH). Ne modifie pas le snapshot.
        - action: "prev" | "next" | "jump" | "submit"
        - posted_cta: CTA choisie (utile pour "jump" ciblé)
        """
        # submit => fin
        if action == "submit":
            return FINISH

        # Cas initial (courant vide) : on va à la première visible
        if not current_key:
            return self.first_visible_step_key(snapshot)

        step = self.get_step(current_key)

        # prev : remonte à la step visible précédente (ne touche pas aux données)
        if action == "prev":
            prev_key = self.prev_visible_step_key(current_key, snapshot)
            return prev_key or current_key  # si pas de prev, rester

        # jump : suit la CTA vers next_step (si fourni), sinon reste
        if action == "jump":
            if posted_cta and posted_cta.next_step:
                return posted_cta.next_step
            # fallback : si pas de cible, reste sur place
            return current_key

        # next : si transitions conditionnelles définies, les évaluer
        if action == "next":
            target = self._apply_step_transitions(step, snapshot)
            if target:
                return target
            # sinon next visible
            return self.next_visible_step_key(current_key, snapshot) or FINISH

        # action inconnue => ne pas bouger
        return current_key