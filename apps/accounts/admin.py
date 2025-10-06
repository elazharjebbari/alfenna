from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from .models import StudentProfile


class StudentProfileInline(admin.StackedInline):
    model = StudentProfile
    can_delete = False
    verbose_name_plural = "Profil étudiant"


class CustomUserAdmin(UserAdmin):
    inlines = (StudentProfileInline,)


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)
