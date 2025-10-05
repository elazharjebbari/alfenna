# Lecture multi-langues — Guide d'intégration

Ce guide couvre la mise en place du streaming MP4 multi-langues (FR/AR), l'ingestion automatisée des fichiers et le seed complet du cours « Fabrication de bougies ».

## 1. Modèle de données
- `LanguageCode` (choices) expose `fr_FR` et `ar_MA`.
- `LectureVideoVariant` référence une `Lecture`, la langue, un chemin (`storage_path`) ou un `FileField`, et un booléen `is_default`.
- Contrainte d'unicité `(lecture, lang)` et timestamp `created_at/updated_at`.

## 2. Vue de streaming (`learning:stream`)
- Paramètre `?lang=fr_FR|ar_MA`. À défaut, la vue analyse `Accept-Language`.
- Sélectionne la variante correspondante (priorité : requête → Accept-Language → variant par défaut → variante FR → fallback `Lecture.video_path` / `lecture.video_file`).
- Réponse HTTP : `206 Partial Content` avec Range/ETag conservés, header `Content-Language`, `Vary: Accept-Language`, `Cache-Control: private, no-store`.

## 3. Hydrateur Atelier (`video_player`)
- Précharge les variantes (`lecture.video_variants`) lors du calcul du contexte.
- Expose :
  - `stream_url` déjà suffixé par `?lang=<code>`.
  - `video_variants` (mapping `{lang: url}`) pour l’UI.
  - `active_lang` déterminé à partir des paramètres de requête / variantes disponibles.

## 4. Script d’ingestion (`apps/content/scripts/ingest_multilang_variants.py`)
- Scanne :
  - FR : `media/videos/stream/fr_france/**/*.mp4`
  - AR : `media/videos/strem/ar_maroc/**/*.mp4` et `media/videos/stream/ar_maroc/**/*.mp4`
- Nettoie les suffixes aléatoires (ex. `_KtwWjO_…`), normalise les clés et apparie par préfixe numérique ou slug du titre.
- Produit un plan (`create` / `update` / `noop` / `orphan`).
- Dry-run par défaut ; `--apply` persiste (`transaction.atomic`).
- Logging détaillé, idempotence garantie (2ᵉ run ⇒ 0 création/mise à jour).

### Commandes utiles
```bash
python manage.py runscript apps.content.scripts.ingest_multilang_variants --script-args "course_slug=<slug>"
python manage.py runscript apps.content.scripts.ingest_multilang_variants --script-args "course_slug=<slug> --apply"
```

## 5. Tests associés
- Unitaire : `apps/content/tests/test_video_variants.py`
- Intégration streaming : `apps/learning/tests/test_stream_multilang.py`
- Hydrateur : `apps/atelier/tests/test_learning_video_player.py`
- Smokes runscript :
  - `apps/content/scripts/suite/tests_scripts/test_ingest_multilang.py`
  - `apps/learning/scripts/suite/tests_scripts/test_stream_range_lang_smoke.py`
  - `apps/atelier/scripts/suite/tests_scripts/test_learn_multilang_smoke.py`

## 6. Migration de seed (existant)
- `0005_seed_multilang_variants` rattache initialement :
  - `videos/stream/fr_france/1_-_Introduction_et_presentation_du_materiels.mp4`
  - `videos/strem/ar_maroc/1_-_Introduction_et_presentation_du_materiels.mp4`
  - `videos/stream/fr_france/4_-_Presentation_des_meches.mp4`
  - `videos/strem/ar_maroc/4_-_Presentation_des_meches.mp4`
- Après `python manage.py migrate`, les variantes FR (défaut) et AR sont disponibles.

## 7. Seed complet « Fabrication de bougies »
- Script : `python manage.py runscript apps.content.scripts.seed_bougie_multilang`
- Fonctionnalités :
  - supprime puis recrée le cours `fabrication-de-bougie` (4 sections, `free_lectures_count=2`).
  - crée les lectures d’après les préfixes (`1`, `1-1`, `…`, `14`).
  - marque `1` et `2-1` en gratuit/démo, laisse le reste premium.
  - attribue `video_path` à partir de la version FR si disponible.
  - rattache directement les variantes FR/AR (FR = défaut) en s’appuyant sur les chemins détectés.
- Idempotent : chaque exécution repart d’un état propre.

## 8. Résumé des commandes/tests
```bash
python manage.py test apps.content.tests.test_video_variants -v2
python manage.py test apps.learning.tests.test_stream_multilang -v2
python manage.py test apps.atelier.tests.test_learning_video_player -v2
python manage.py runscript apps.content.scripts.suite.run_all
python manage.py runscript apps.learning.scripts.suite.run_all
python manage.py runscript apps.atelier.scripts.suite.tests_scripts.test_learn_multilang_smoke
```

## 9. Exploitation quotidienne
- Gestion via l’admin : inline `LectureVideoVariant` dans `LectureAdmin` (champs `lang`, `file`, `storage_path`, `is_default`).
- En production, utiliser le dry-run de l’ingestion avant `--apply`.
- Les logs `stream` mentionnent la langue servie (`stream_response`) et signalent les fichiers manquants (`stream_variant_missing`).
- Pour rollback : supprimer l’usage des variantes dans `VideoStreamView` (fallback `_storage_path_and_size`), rerun `seed_bougie_multilang` pour recharger la structure si besoin.

## 10. Vérifications d'accès
- Créer/mettre à jour l’utilisateur de test :
  ```bash
  python manage.py runscript apps.accounts.scripts.ensure_buyer_fixture --script-args "password=Password-2025"
  python manage.py runscript apps.accounts.scripts.ensure_buyer_fixture --script-args "password=Password-2025 --entitle"
  ```
- Vérifier les règles d’accès (free vs premium, FR/AR) :
  ```bash
  python manage.py runscript apps.learning.scripts.verify_access_buyer
  python manage.py test apps.learning.tests.test_access_buyer_smoke -v2
  ```
