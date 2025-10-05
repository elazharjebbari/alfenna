from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile", unique=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(blank=True, null=True)
    marketing_opt_in = models.BooleanField(default=False)
    marketing_opt_out_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Profil étudiant"
        verbose_name_plural = "Profils étudiants"
        constraints = [
            models.UniqueConstraint(fields=["user"], name="unique_user_profile")
        ]
    def __str__(self):
        return f"Profil de {self.user.username}"
