from __future__ import annotations
from django.db import models
from django.utils import timezone

class FlowStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    COMPLETED = "COMPLETED", "Completed"
    ABANDONED = "ABANDONED", "Abandoned"

class FlowSession(models.Model):
    """
    Journal d’avancement d’un flow pour un visiteur (clé = flow_key + session_key).
    Sert à:
      - Reprendre un flow interrompu
      - Consolider un Lead (merge ou création)
      - Planifier des relances (abandon)
    """
    flow_key = models.SlugField(max_length=64)
    session_key = models.CharField(max_length=64, db_index=True)
    lead = models.ForeignKey("leads.Lead", null=True, blank=True, on_delete=models.SET_NULL, related_name="flow_sessions")

    current_step = models.CharField(max_length=64, blank=True, default="")
    data_snapshot = models.JSONField(default=dict, blank=True)

    status = models.CharField(max_length=16, choices=FlowStatus.choices, default=FlowStatus.ACTIVE)
    reminder_count = models.PositiveIntegerField(default=0)
    scheduled_reminder_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    last_touch_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = (("flow_key", "session_key"),)
        indexes = [
            models.Index(fields=["flow_key", "session_key"]),
            models.Index(fields=["status"]),
            models.Index(fields=["last_touch_at"]),
        ]

    def touch(self):
        self.last_touch_at = timezone.now()
        self.save(update_fields=["last_touch_at", "updated_at"])

    def __str__(self) -> str:
        lid = self.lead_id or "-"
        return f"FlowSession[{self.flow_key}/{self.session_key}] lead={lid} step={self.current_step or '-'}"