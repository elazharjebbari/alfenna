from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("i18n", "0001_initial"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="stringtranslation",
            name="i18n_string_mo_ba0509_idx",
        ),
        migrations.AddIndex(
            model_name="stringtranslation",
            index=models.Index(
                fields=["model_label", "object_id", "field", "language"],
                name="i18n_string_model_l_1a96d1_idx",
            ),
        ),
    ]
