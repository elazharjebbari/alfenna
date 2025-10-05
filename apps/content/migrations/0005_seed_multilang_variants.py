from django.db import migrations


def seed_video_variants(apps, schema_editor):
    Lecture = apps.get_model("content", "Lecture")
    LectureVideoVariant = apps.get_model("content", "LectureVideoVariant")

    targets = [
        {
            "course_slug": "bougies-naturelles",
            "section_order": 1,
            "lecture_order": 1,
            "variants": {
                "fr_FR": "videos/stream/fr_france/1_-_Introduction_et_presentation_du_materiels.mp4",
                "ar_MA": "videos/strem/ar_maroc/1_-_Introduction_et_presentation_du_materiels.mp4",
            },
        },
        {
            "course_slug": "bougies-naturelles",
            "section_order": 4,
            "lecture_order": 1,
            "variants": {
                "fr_FR": "videos/stream/fr_france/4_-_Presentation_des_meches.mp4",
                "ar_MA": "videos/strem/ar_maroc/4_-_Presentation_des_meches.mp4",
            },
        },
    ]

    for entry in targets:
        lecture = (
            Lecture.objects.filter(
                course__slug=entry["course_slug"],
                section__order=entry["section_order"],
                order=entry["lecture_order"],
            )
            .select_related("section", "course")
            .first()
        )
        if lecture is None:
            continue

        for lang, path in entry["variants"].items():
            obj, created = LectureVideoVariant.objects.get_or_create(
                lecture=lecture,
                lang=lang,
                defaults={
                    "storage_path": path,
                    "is_default": lang == "fr_FR",
                },
            )
            if not created:
                updated = False
                if obj.storage_path != path:
                    obj.storage_path = path
                    updated = True
                if lang == "fr_FR" and not obj.is_default:
                    obj.is_default = True
                    updated = True
                if updated:
                    obj.save(update_fields=["storage_path", "is_default", "updated_at"])


def unseed_video_variants(apps, schema_editor):
    LectureVideoVariant = apps.get_model("content", "LectureVideoVariant")
    LectureVideoVariant.objects.filter(
        lecture__course__slug="bougies-naturelles",
        lang__in=["fr_FR", "ar_MA"],
        storage_path__in=[
            "videos/stream/fr_france/1_-_Introduction_et_presentation_du_materiels.mp4",
            "videos/strem/ar_maroc/1_-_Introduction_et_presentation_du_materiels.mp4",
            "videos/stream/fr_france/4_-_Presentation_des_meches.mp4",
            "videos/strem/ar_maroc/4_-_Presentation_des_meches.mp4",
        ],
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0004_lecturevideovariant"),
    ]

    operations = [
        migrations.RunPython(seed_video_variants, unseed_video_variants),
    ]
