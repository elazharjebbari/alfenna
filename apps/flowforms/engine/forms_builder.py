# apps/flowforms/engine/forms_builder.py
from __future__ import annotations

from typing import Any, Dict, List, Tuple
from dataclasses import dataclass

from django import forms
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError

from apps.leads.models import Lead
from apps.leads.validators import is_valid_email, is_valid_phone, is_valid_postal

# ------------------------------------------------------------
# Validators mapping (extensible via settings.FLOWFORMS_VALIDATORS_MAP)
# ------------------------------------------------------------
_DEFAULT_VALIDATORS_MAP = {
    "email": is_valid_email,
    "phone": is_valid_phone,
    "postal": is_valid_postal,
}

def _get_validators_map() -> Dict[str, Any]:
    user_map = getattr(settings, "FLOWFORMS_VALIDATORS_MAP", None) or {}
    fused = dict(_DEFAULT_VALIDATORS_MAP)
    fused.update(user_map)
    return fused

# ------------------------------------------------------------
# Helpers: field & widget factories
# ------------------------------------------------------------

@dataclass
class FieldSpec:
    name: str
    type: str = "text"
    required: bool = False
    label: str | None = None
    help_text: str | None = None
    max_length: int | None = None
    validators: List[str] = None
    choices: List[Any] | None = None
    widget: str | None = None
    attrs: Dict[str, Any] | None = None

    @classmethod
    def from_config(cls, cfg: Dict[str, Any]) -> "FieldSpec":
        return cls(
            name=cfg["name"],
            type=(cfg.get("type") or "text").lower(),
            required=bool(cfg.get("required", False)),
            label=cfg.get("label"),
            help_text=cfg.get("help_text"),
            max_length=cfg.get("max_length"),
            validators=list(cfg.get("validators") or []),
            choices=list(cfg.get("choices") or []),
            widget=cfg.get("widget"),
            attrs=cfg.get("attrs") or {},
        )

def _coerce_choices(choices: List[Any] | None) -> List[Tuple[str, str]]:
    if not choices:
        return []
    out = []
    for c in choices:
        if isinstance(c, (list, tuple)) and len(c) == 2:
            out.append((str(c[0]), str(c[1])))
        else:
            out.append((str(c), str(c)))
    return out

def _install_validators(spec: FieldSpec, dj_field: forms.Field):
    validators_map = _get_validators_map()
    fn_list = []
    for vname in (spec.validators or []):
        fn = validators_map.get(vname)
        if not fn:
            raise ImproperlyConfigured(f"Validator '{vname}' non déclaré (FLOWFORMS_VALIDATORS_MAP).")
        def _wrap(fn):
            def _validator(value):
                # Bool/checkbox => ignore string validators
                if value in (None, ""):
                    return
                if not fn(value):
                    raise ValidationError(f"Format invalide ({vname}).")
            return _validator
        fn_list.append(_wrap(fn))
    if fn_list:
        dj_field.validators.extend(fn_list)

def _apply_common(dj_field: forms.Field, spec: FieldSpec):
    if spec.label is not None:
        dj_field.label = spec.label
    if spec.help_text is not None:
        dj_field.help_text = spec.help_text
    if spec.attrs:
        # merge attrs dans widget (sans écraser)
        dj_field.widget.attrs = {**dj_field.widget.attrs, **spec.attrs}

def _make_django_field(spec: FieldSpec) -> forms.Field:
    t = spec.type
    required = spec.required
    max_length = spec.max_length

    if t in ("text", "string"):
        f = forms.CharField(required=required, max_length=max_length)
    elif t == "textarea":
        f = forms.CharField(required=required, max_length=max_length, widget=forms.Textarea)
    elif t == "email":
        # on garde EmailField pour HTML5 + nettoyage, et on ajoute notre validator si désiré
        f = forms.EmailField(required=required, max_length=max_length)
    elif t in ("tel", "phone"):
        f = forms.CharField(required=required, max_length=max_length, widget=forms.TextInput(attrs={"inputmode": "tel"}))
    elif t in ("number", "int", "integer"):
        f = forms.IntegerField(required=required)
    elif t == "bool":
        f = forms.BooleanField(required=required)
    elif t in ("select", "radio"):
        choices = _coerce_choices(spec.choices)
        if not choices:
            raise ImproperlyConfigured(f"Le champ '{spec.name}' de type '{t}' requiert des choices[].")
        base = forms.ChoiceField(required=required, choices=choices)
        if t == "radio":
            base.widget = forms.RadioSelect()
        f = base
    elif t == "checkbox":
        # multi-choix
        choices = _coerce_choices(spec.choices)
        if not choices:
            # checkbox simple (bool)
            f = forms.BooleanField(required=required)
        else:
            f = forms.MultipleChoiceField(required=required, choices=choices, widget=forms.CheckboxSelectMultiple)
    elif t == "date":
        f = forms.DateField(required=required, widget=forms.DateInput(attrs={"type": "date"}))
    elif t == "datetime":
        f = forms.DateTimeField(required=required, widget=forms.DateTimeInput(attrs={"type": "datetime-local"}))
    elif t == "file":
        f = forms.FileField(required=required)
    else:
        raise ImproperlyConfigured(f"Type de champ non supporté: {t}")

    _apply_common(f, spec)
    _install_validators(spec, f)
    return f

# ------------------------------------------------------------
# Context proxy: mappe "context.xxx" ⇄ Lead.context["xxx"]
# ------------------------------------------------------------
def _initial_from_instance(instance: Lead, spec: FieldSpec):
    if spec.name.startswith("context."):
        key = spec.name.split(".", 1)[1]
        return (instance.context or {}).get(key)
    # sinon attr du modèle
    return getattr(instance, spec.name, None)

def _save_into_instance(instance: Lead, spec: FieldSpec, value):
    if spec.name.startswith("context."):
        key = spec.name.split(".", 1)[1]
        ctx = dict(instance.context or {})
        # Gestion spéciale file => stocker seulement des métadonnées (nom)
        if spec.type == "file" and value:
            files_meta = dict(ctx.get("__files__", {}))
            files_meta[key] = getattr(value, "name", "upload")
            ctx["__files__"] = files_meta
        else:
            ctx[key] = value
        instance.context = ctx
    else:
        # Champ du modèle Lead
        setattr(instance, spec.name, value)

# ------------------------------------------------------------
# Public API
# ------------------------------------------------------------
def build_form_for_step(step_cfg: Dict[str, Any], *, instance: Lead | None = None, theme_attrs: Dict[str, Any] | None = None) -> forms.ModelForm:
    """
    Construit dynamiquement un ModelForm lié à Lead, limité aux champs définis
    dans step_cfg["fields"].

    - Supporte context.* (JSON proxy)
    - Injecte attrs CSS (theme_attrs au niveau du form + attrs par champ dans la config)
    - Attache validators (map configurable)
    """
    if not step_cfg or "fields" not in step_cfg:
        raise ImproperlyConfigured("step_cfg invalide : 'fields' attendu.")

    # Préparer FieldSpec
    field_specs = [FieldSpec.from_config(f) for f in (step_cfg.get("fields") or [])]
    # Sécurité: vérifier existence dans Lead ou context
    lead_fields = {f.name for f in Lead._meta.get_fields() if hasattr(f, "name")}
    for spec in field_specs:
        if not (spec.name in lead_fields or spec.name.startswith("context.")):
            raise ImproperlyConfigured(f"Champ '{spec.name}' non reconnu (Lead ou context.*).")

    # Champs "purs" Lead pour Meta.fields
    meta_fields = [s.name for s in field_specs if not s.name.startswith("context.")]
    # Toujours autoriser un sous-ensemble strict
    class _DynamicForm(forms.ModelForm):
        class Meta:
            model = Lead
            fields = meta_fields

        def __init__(self, *args, **kwargs):
            _instance = kwargs.get("instance")
            super().__init__(*args, **kwargs)

            # Thème (attrs globaux)
            if theme_attrs:
                for k, v in (theme_attrs or {}).items():
                    self.attrs = getattr(self, "attrs", {})
                    self.attrs[k] = v

            # Installer dynamiquement les champs (y compris context.*)
            # D’abord retirer les champs Meta existants (pour repartir propre)
            for name in list(self.fields.keys()):
                if name not in [s.name for s in field_specs if not s.name.startswith("context.")]:
                    self.fields.pop(name)

            for spec in field_specs:
                f = _make_django_field(spec)
                # initial
                if _instance is not None:
                    init_val = _initial_from_instance(_instance, spec)
                    if init_val not in (None, ""):
                        f.initial = init_val
                self.fields[spec.name] = f

        def clean(self):
            # Laisse Django nettoyer chaque champ (validators custom déjà branchés)
            return super().clean()

        def save(self, commit=True):
            if self.instance is None:
                raise ImproperlyConfigured("build_form_for_step() requiert 'instance' (Lead).")
            # On sauvegarde d’abord les champs Lead via super()
            # mais attention: on a ajouté des champs context.* qui ne sont pas dans Meta.fields
            # => on leur applique le bridge à la main
            lead_obj: Lead = self.instance
            for name, val in self.cleaned_data.items():
                spec = next((s for s in field_specs if s.name == name), None)
                if not spec:
                    continue
                if spec.name.startswith("context."):
                    _save_into_instance(lead_obj, spec, val)
                else:
                    setattr(lead_obj, spec.name, val)

            if commit:
                lead_obj.save()
            return lead_obj

    # Instancier le form
    form = _DynamicForm(instance=instance)
    return form