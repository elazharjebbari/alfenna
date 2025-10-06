from django.conf import settings
from django.db import models

class Progress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="learning_progress")
    lecture = models.ForeignKey("content.Lecture", on_delete=models.CASCADE, related_name="progress_entries")
    # P0: progression simple + position optionnelle pour reprise
    is_completed = models.BooleanField(default=False)
    last_position_ms = models.PositiveIntegerField(default=0)
    last_viewed_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = (("user", "lecture"),)
        indexes = [
            models.Index(fields=["user", "lecture"]),
            models.Index(fields=["lecture", "is_completed"]),
        ]

    def __str__(self):
        return f"Progress(user={self.user_id}, lecture={self.lecture_id}, completed={self.is_completed})"


class LectureComment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lecture_comments")
    lecture = models.ForeignKey("content.Lecture", on_delete=models.CASCADE, related_name="comments")
    body = models.TextField(max_length=2000)
    is_visible = models.BooleanField(default=True)
    is_flagged = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["lecture", "created_at"]),
            models.Index(fields=["user", "lecture"]),
        ]

    def __str__(self):
        return f"Comment({self.user_id} on {self.lecture_id})"
