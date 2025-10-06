# Variants & Rollout

Ce document résume le fonctionnement du système de variantes configurables côté Atelier (headers et futures expériences).

## Vue d'ensemble

1. **Cookie de bucketing** : `ABBucketingCookieMiddleware` (`apps/atelier/ab/middleware.py`) s'assure que chaque visiteur dispose d'un cookie `ll_ab`. Il est long de 32 caractères hex et vit ~6 mois. La valeur reste stable pour garantir une affectation déterministe.
2. **Décision de variante** : `resolve_variant` (`apps/atelier/ab/waffle.py`) calcule un bucket 0..99 en utilisant, dans l'ordre, `user.pk`, `ll_ab` ou l'adresse IP. Le bucket est comparé au `rollout` défini pour l'expérience.
3. **Configurations YAML** : `get_experiments_spec` fusionne la config `core` et le namespace courant (`apps/atelier/config/loader.py`). On décrit les slots dans `pages.yml` et les expériences dans `experiments.yml`.
4. **Pipeline de rendu** : `build_page_spec` (`apps/atelier/compose/pipeline.py`) passe la variante au template (`variant_key`) et construit la clé de cache qui inclut `variant_key` + suffixe `|qa` si une preview est active.
5. **Instrumentation** : `static/site/analytics.js` enveloppe `window.dataLayer` pour rattacher chaque `push` aux événements observables (`datalayer:push`). Les attributs HTML `data-ll-*` portent la variante retenue.

## Déclarer une expérience A/B

### 1. Décrire les variantes dans le slot (`pages.yml`)

```yaml
a_page:
  slots:
    header:
      experiment: header_ab
      variants:
        A: "header/modes"
        B: "header/struct"
      cache: false
```

- `experiment` : identifiant logique (sans espace). Utilisé pour la résolution et la QA preview.
- `variants` : mapping des clés (`A`, `B`, ...). Chaque valeur est un alias de composant (namespace facultatif).
- `cache` : le cache peut rester activé, la clé sera automatiquement différente par variante.

### 2. Définir l'expérience (`experiments.yml`)

```yaml
experiments:
  header_ab:
    rollout: 0
```

- `rollout` est un entier 0..100 :
  - `0` = 100 % de trafic sur `A`.
  - `100` = 100 % sur `B` (si déclarée).
  - Valeurs intermédiaires distribuent `B` pour les buckets `< rollout`.
- On peut surcharger par namespace (ex. `fr`, `ma`) pour découper la montée en charge ou appliquer un variant différent selon le pays.

> ⚠️ Les `variants` peuvent aussi être décrits dans `experiments.yml` pour centraliser, mais la définition au niveau du slot reste prioritaire.

## Comment fonctionne `rollout`

```
 bucket = sha1(seed)[0:4] → int % 100
 if bucket < rollout and "B" est disponible → renvoie B
 sinon → renvoie A (ou la première variante disponible)
```

- `seed` = `user.pk` si présent, sinon cookie `ll_ab`, sinon IP.
- `rollout` doit rester un entier (les valeurs non numériques retombent à 0).
- Un `rollout` supérieur à 100 est ramené à 100 ; inférieur à 0 ⇒ 0.

## QA & Preview

- Ajoutez `?dwft_<experiment>=1` (ex. `?dwft_header_ab=1`) à l'URL pour activer le mode preview.
- La résolution reste inchangée (mêmes buckets), mais la clé de cache se termine par `|qa` afin d'éviter la pollution du cache partagé.
- Pendant une preview, `slot_ctx["qa_preview"]` passe à `True` et l'attribut HTML `data-ll-cache-key` intègre le suffixe.

## Instrumentation & Tracking

- Les slots rendus portent `data-ll-variant="A|B"`. Dans les templates header core, l'attribut `data-ab-variant="{{ variant_key }}` est ajouté pour faciliter les tests visuels.
- `analytics.js` encapsule `window.dataLayer` :
  - `dataLayer.push(payload)` normalise l'événement (UUID, timestamp, attributs) et l'envoie au batcher.
  - Chaque push déclenche un `CustomEvent('datalayer:push')` + callbacks enregistrés via `dataLayer.on(listener)`.

## Étapes pour lancer un rollout

1. **Vérifier** que les deux variants rendent correctement (tests unitaires/Playwright + QA visuelle).
2. **Mettre à jour** `rollout` dans les YAML du namespace visé :
   - `rollout: 1` (1 %), déploiement.
   - Observer les métriques (slots `data-ll-variant`).
   - Continuer vers `5`, `10`, … jusqu'à `100`. Revenir à `0` en cas de rollback instantané.
3. **Tests** :
   - `python manage.py test apps.atelier.tests.test_ab_variants -v 2`
   - Bundled smoke : `python manage.py test apps.atelier.tests -v 2`

## Ajouter un nouveau test / debug

- Les cas critiques sont couverts dans `apps/atelier/tests/test_ab_variants.py`.
- Pour reproduire un bucket précis, mocker `_stable_bucket` ou forcer `ll_ab` dans la requête.
- Les clés de cache incluent `variant_key`, `site_version`, `content_rev`, `qa` → inspecter via `services.build_cache_key` pour confirmer l'isolement.

## Check-list quand vous créez une nouvelle expérience

- [ ] Identifiant unique (`experiment`) cohérent dans `pages.yml`.
- [ ] Définition du `rollout` dans `experiments.yml` (core + namespaces nécessaires).
- [ ] Templates/partials prêts pour toutes les variantes (marquage facultatif `data-ab-variant`).
- [ ] Tests unitaires ou snapshots couvrant A & B.
- [ ] Prévoir un plan de retour arrière (`rollout: 0`).

Bonnes créations de variantes !
