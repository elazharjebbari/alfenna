# Rapport diagnostic SEO — Blocage robots

## Origine du problème
- Le middleware `SeoGuardMiddleware` (`apps/marketing/middleware.py:16`) force `X-Robots-Tag: noindex, nofollow` dès que `SEO_ENV` n'est pas `"prod"`; en production l'absence de variable d'environnement `SEO_ENV` laissait la valeur par défaut `"dev"` (`lumierelearning/settings/base.py:369`).
- Aucun en-tête `X-Robots-Tag` contradictoire n'était injecté côté OpenLiteSpeed ou dans les templates publics, confirmant que le blocage provenait bien de la couche Django.

## Correction appliquée
- Surchargé systématiquement `SEO_ENV` à `"prod"` dans la configuration de production (`lumierelearning/settings/prod.py:6`) afin d'empêcher `SeoGuardMiddleware` de bloquer l'indexation des pages publiques.
- Ajouté `RobotsTagMiddleware` qui complète la politique robots : il garantit `index, follow` dès qu'aucun en-tête n'est défini, tout en imposant `noindex, nofollow` sur les préfixes privés (`apps/core/middleware/robots.py:8`), et enregistré ce middleware dans la pile (`lumierelearning/settings/base.py:110`).
- Documenté les préfixes privés additionnels dans les réglages (`lumierelearning/settings/base.py:372`) pour expliciter la protection de `/admin/` et `/staging/`.

## Bonnes pratiques SEO futures
- Vérifier avant chaque mise en production que `SEO_ENV` est bien défini à `"prod"` et exécuter le smoke test `python manage.py runscript apps.pages.scripts.smoke_seo_headers --settings=lumierelearning.settings.test_cli`.
- Intégrer dans la CI le test `apps/pages/tests/test_robots_headers.py` afin de détecter toute régression future sur l'en-tête `X-Robots-Tag`.
- Limiter l'usage de `noindex` aux routes explicitement privées et surveiller les nouveaux middlewares ou templates qui pourraient réintroduire des directives bloquantes.
