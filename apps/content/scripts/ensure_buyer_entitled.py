# -*- coding: utf-8 -*-
from __future__ import annotations
import shlex
from typing import Iterable
from django.contrib.auth import get_user_model
from django.utils.timezone import now
from django.db import transaction
from apps.catalog.models.models import Course
# adapte l'import Entitlement à ton projet si le chemin diffère
from apps.billing.models import Entitlement

def _parse(argv: Iterable[str] | None):
    args = {"username":"buyer_access","password":"Password-2025","course_slug":"bougies-naturelles","entitle":"1"}
    tokens = shlex.split(" ".join(argv or ()))
    for t in tokens:
        if "=" in t:
            k,v = t.split("=",1); args[k]=v
        elif t == "--no-entitle":
            args["entitle"] = "0"
    return args

@transaction.atomic
def run(*args, **kwargs):
    params = _parse(kwargs.get("script_args") or args)
    User = get_user_model()
    user, _ = User.objects.get_or_create(username=params["username"], defaults={"email":"buyer_access@example.com","is_active":True})
    if params.get("password"):
        user.set_password(params["password"]); user.is_active=True; user.save(update_fields=["password","is_active"])
    course = Course.objects.get(slug=params["course_slug"])
    msg = [f"user_id={user.id}", f"course_id={course.id}"]

    if params["entitle"] == "1":
        ent, created = Entitlement.objects.get_or_create(user=user, course=course, defaults={"granted_at": now()})
        if not created:
            # réactualise la date si tu veux
            ent.granted_at = now(); ent.save(update_fields=["granted_at"])
        msg.append("entitlement=ON")
    else:
        Entitlement.objects.filter(user=user, course=course).delete()
        msg.append("entitlement=OFF")

    print(" | ".join(msg))
