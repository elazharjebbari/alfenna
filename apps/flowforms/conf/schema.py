# apps/flowforms/conf/schema.py
from typing import List, Optional, Dict, Literal, Any
from pydantic import BaseModel

class FieldConfig(BaseModel):
    name: str
    type: Literal["text", "email", "phone", "date", "datetime", "number",
                  "bool", "select", "radio", "checkbox", "textarea", "file"] = "text"
    required: bool = False
    label: Optional[str] = None
    help_text: Optional[str] = None
    max_length: Optional[int] = None
    validators: List[str] = []
    choices: Optional[List[str]] = None
    widget: Optional[str] = None
    # attrs optionnel pour styler les widgets (déjà supporté par le builder)
    attrs: Optional[Dict[str, Any]] = None

class CTAConfig(BaseModel):
    action: Literal["next", "prev", "submit", "jump"] = "next"
    label: str
    confirm: Optional[str] = None
    next_step: Optional[str] = None
    class_name: Optional[str] = None

class ConditionConfig(BaseModel):
    field: str
    op: Literal["equals", "not_equals", "in", "not_in", "is_true", "is_false"]
    value: Optional[Any] = None
    next: Optional[str] = None

class StepConfig(BaseModel):
    key: str
    title: Optional[str]
    fields: List[FieldConfig] = []
    ctas: List[CTAConfig] = []
    # Transitions de step (ex: si X alors aller vers step Y)
    conditions: List[ConditionConfig] = []
    # Optionnel : visibilité conditionnelle de la step
    show_if: Optional[List[ConditionConfig]] = None

class FlowConfig(BaseModel):
    key: str
    kind: str
    steps: List[StepConfig]
    abandon_ttl_minutes: int = 45
    max_reminders: int = 2

class FlowFormsConfig(BaseModel):
    flows: List[FlowConfig]

    def get_flow(self, key: str) -> FlowConfig:
        for f in self.flows:
            if f.key == key:
                return f
        raise KeyError(f"Flow {key} not found")