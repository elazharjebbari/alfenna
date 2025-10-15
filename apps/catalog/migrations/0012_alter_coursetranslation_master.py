import django.db.models.deletion
import parler.fields
from django.db import migrations, models
from django.db.migrations.operations.base import Operation

import parler.models


class AlterCourseModelBases(Operation):
    """
    Update the historical Course model so parler recognises it as translatable
    before CourseTranslation relationships are reloaded.
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
        # State-only adjustment.
        pass

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        # State-only adjustment.
        pass

    def describe(self):
        return f"Alter {self.name} model bases to parler.TranslatableModel"


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0011_coursetranslation_and_more"),
    ]

    operations = [
        AlterCourseModelBases(
            name="Course",
            new_bases=(parler.models.TranslatableModel,),
            old_bases=(models.Model,),
        ),
        migrations.AlterField(
            model_name="coursetranslation",
            name="master",
            field=parler.fields.TranslationsForeignKey(
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="translations",
                to="catalog.course",
            ),
        ),
    ]
