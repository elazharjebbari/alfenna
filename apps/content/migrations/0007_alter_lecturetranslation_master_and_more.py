import django.db.models.deletion
from django.db import migrations, models
from django.db.migrations.operations.base import Operation

import parler.fields
import parler.models


class AlterModelBases(Operation):
    """
    Ensure historical Section/Lecture models use TranslatableModel so parler
    can attach translation metadata during migrations.
    """

    reduces_to_sql = True
    reversible = True

    def __init__(self, name, new_bases, old_bases):
        self.name = name
        self.new_bases = new_bases
        self.old_bases = old_bases

    def state_forwards(self, app_label, state):
        model_state = state.models[app_label, self.name.lower()]
        cloned = model_state.clone()
        cloned.bases = self.new_bases
        state.models[app_label, self.name.lower()] = cloned
        state.reload_model(app_label, self.name.lower(), delay=True)

    def state_backwards(self, app_label, state):
        model_state = state.models[app_label, self.name.lower()]
        cloned = model_state.clone()
        cloned.bases = self.old_bases
        state.models[app_label, self.name.lower()] = cloned
        state.reload_model(app_label, self.name.lower(), delay=True)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        pass

    def describe(self):
        return f"Alter {self.name} model bases to parler.TranslatableModel"


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0006_remove_lecture_title_remove_section_title_and_more"),
    ]

    operations = [
        AlterModelBases(
            name="Section",
            new_bases=(parler.models.TranslatableModel,),
            old_bases=(models.Model,),
        ),
        AlterModelBases(
            name="Lecture",
            new_bases=(parler.models.TranslatableModel,),
            old_bases=(models.Model,),
        ),
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
