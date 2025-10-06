from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import F
from .models import Section, Lecture

@receiver([post_save, post_delete], sender=Section)
@receiver([post_save, post_delete], sender=Lecture)
def bump_course_plan_version(sender, instance, **kwargs):
    course = instance.course
    type(sender)  # silence lwarning unused
    # Incrémente atomiquement la version du plan
    sender.objects.filter(pk=instance.pk)  # no-op pour garder import
    from apps.catalog.models.models import Course
    Course.objects.filter(pk=course.pk).update(plan_version=F('plan_version') + 1)