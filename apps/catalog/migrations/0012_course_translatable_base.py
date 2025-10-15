from django.db import migrations, models
from django.db.migrations.operations.base import Operation

import parler.models

from apps.catalog.models.models import CourseManager


class AlterCourseModelBases(Operation):
    """
    Ensure the historical Course model inherits from TranslatableModel so that
    parler can register its translation meta during migrations.
    """

    reduces_to_sql = True
    reversible = True

    def __init__(self, name, new_bases, old_bases):
        self.name = name
        self.new_bases = new_bases
        self.old_bases = old_bases

    def state_forwards(self, app_label, state):
        model_state = state.models[app_label, self.name.lower()]
        updated_state = model_state.clone()
        updated_state.bases = self.new_bases
        state.models[app_label, self.name.lower()] = updated_state
        state.reload_model(app_label, self.name.lower(), delay=True)

    def state_backwards(self, app_label, state):
        model_state = state.models[app_label, self.name.lower()]
        updated_state = model_state.clone()
        updated_state.bases = self.old_bases
        state.models[app_label, self.name.lower()] = updated_state
        state.reload_model(app_label, self.name.lower(), delay=True)

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        # No database changes required; this keeps model state in sync.
        pass

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        # No database changes required; this keeps model state in sync.
        pass

    def describe(self):
        return f"Alter {self.name} model bases to use parler.TranslatableModel"


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
        migrations.AlterModelManagers(
            name="course",
            managers=[
                ("objects", CourseManager()),
            ],
        ),
    ]
