import django.db.models.deletion
import parler.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0006_remove_lecture_title_remove_section_title_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="lecturetranslation",
            name="master",
            field=parler.fields.TranslationsForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="translations",
                to="content.lecture",
            ),
        ),
        migrations.AlterField(
            model_name="sectiontranslation",
            name="master",
            field=parler.fields.TranslationsForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="translations",
                to="content.section",
            ),
        ),
    ]
