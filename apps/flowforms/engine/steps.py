# apps/flowforms/engine/steps.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

@dataclass(frozen=True)
class Condition:
    field: str
    op: str
    value: Any = None
    next: Optional[str] = None  # utilisé pour transition

    @staticmethod
    def _get_value(snapshot: Dict[str, Any], field: str) -> Any:
        # support "context.xxx" dans snapshot
        if field.startswith("context."):
            ctx = snapshot.get("context", {})
            return ctx.get(field.split(".", 1)[1])
        return snapshot.get(field)

    def evaluate(self, snapshot: Dict[str, Any]) -> bool:
        left = self._get_value(snapshot, self.field)
        op = self.op
        right = self.value
        if op == "equals":
            return left == right
        if op == "not_equals":
            return left != right
        if op == "in":
            try:
                return left in (right or [])
            except TypeError:
                return False
        if op == "not_in":
            try:
                return left not in (right or [])
            except TypeError:
                return True
        if op == "is_true":
            return bool(left) is True
        if op == "is_false":
            return bool(left) is False
        # opérateur inconnu => sécurité : False
        return False

@dataclass(frozen=True)
class CTA:
    action: str  # next/prev/submit/jump
    label: str
    next_step: Optional[str] = None
    confirm: Optional[str] = None
    class_name: Optional[str] = None

@dataclass(frozen=True)
class Step:
    key: str
    title: Optional[str]
    fields: List[Dict[str, Any]]
    ctas: List[CTA]
    transitions: List[Condition]
    show_if: List[Condition]

    @classmethod
    def from_config(cls, step_cfg: Dict[str, Any]) -> "Step":
        ctas = [CTA(
            action=c.get("action", "next"),
            label=c["label"],
            next_step=c.get("next_step"),
            confirm=c.get("confirm"),
            class_name=c.get("class_name")
        ) for c in (step_cfg.get("ctas") or [])]

        trans = [Condition(
            field=t["field"],
            op=t["op"],
            value=t.get("value"),
            next=t.get("next"),
        ) for t in (step_cfg.get("conditions") or [])]

        show_if = [Condition(
            field=t["field"],
            op=t["op"],
            value=t.get("value"),
        ) for t in (step_cfg.get("show_if") or [])]

        return cls(
            key=step_cfg["key"],
            title=step_cfg.get("title"),
            fields=step_cfg.get("fields") or [],
            ctas=ctas,
            transitions=trans,
            show_if=show_if,
        )