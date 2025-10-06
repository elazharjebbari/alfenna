TITRE — Chatbot Feature Flag “Hard OFF” (aucune trace front)

## Contexte & objectifs
Ajouter un flag runtime `CHATBOT_ENABLED` permettant de désactiver totalement le chat côté front: aucun DOM, aucun asset, aucune route.

Éviter tout résidu: pas d’élément `[data-chatbot]`, pas de `static/js/chatbot*.js`, pas de `/api/chat/*`, pas d’appel SSE. Séparer les caches ON/OFF.

## Contraintes & frontières
- Périmètre autorisé: `apps/atelier/**`, `apps/chatbot/**`, `templates/**`, `lumierelearning/{settings,urls.py}`, `tests/**`.
- Interdits: `lumierelearning/OnlineLearning (excluded)/**`.
- Sécurité/Perf: variation de cache par flag, zéro route exposée si OFF, 0 appel réseau chat.

## Design attendu (haut niveau)
- Flag: `CHATBOT_ENABLED` (bool ENV).
- Routing: monter `/api/chat/*` uniquement si ON.
- Pipeline: stripper des slots qui retire toute entrée `component: chatbot/*` avant collecte des assets.
- Cache key: append `|ff:cb:{0|1}` à la révision de contenu stable pour cloisonner ON/OFF.
- Fallback: si OFF, toute tentative legacy sur `/api/chat/*` doit 404.

## Plan d’implémentation (steps atomiques)
1. **Settings**
   - Ajouter le flag: `CHATBOT_ENABLED = env_flag('CHATBOT_ENABLED', default=True)` dans `lumierelearning/settings/base.py`.
   - Exposer ce flag aux templates via le context processor Atelier existant si nécessaire (optionnel).
   - Tests: assert que `settings.CHATBOT_ENABLED` lit bien l’ENV.

2. **URLs**
   - Éditer `lumierelearning/urls.py`: si `settings.CHATBOT_ENABLED`, inclure `path('api/chat/', include('apps.chatbot.urls'))`. Sinon, ne rien inclure et, optionnellement, `re_path(r'^api/chat/.*$', deadend_404)` uniquement pour tests.
   - Tests: client Django `GET /api/chat/start` renvoie 404 quand OFF, 405/403/200 selon cas quand ON.

3. **Pipeline — strip des slots chatbot/**
   - Dans `apps/atelier/compose/pipeline.py`, ajouter un filtre qui supprime toute entrée dont le composant (ou son alias effectif) commence par `chatbot/` lorsque `CHATBOT_ENABLED` est faux.
   - Ajouter la variation du cache de page: append `|ff:cb:{int(settings.CHATBOT_ENABLED)}` à la révision de contenu stable.
   - Tests unitaires: charger une page dont la YAML contient `component: chatbot/shell` et vérifier qu’en OFF, `render_page()` ne rend aucun wrapper `[data-chatbot]` ni assets `chatbot*.js`.

4. **Garde-fou template (optionnel)**
   - Dans `templates/components/chatbot/*`, encapsuler par `{% if chatbot_enabled %}`. Cela ne devrait jamais s’exécuter si OFF, c’est juste pour éviter les surprises en refacto.

5. **E2E Playwright**
   - Créer `tests/e2e/test_chatbot_off.py`: contexte OFF, vérifier absence DOM/scripts chat et absence de requêtes `/api/chat/*`.

## Conventions YAML & templates
- Ne retire pas “à la main” le slot `chatbot/shell` des YAML. Le pipeline doit le stripper dynamiquement selon le flag.
- Aucun texte/URL en dur côté template chat; on est dans le “non rendu” complet si OFF.

## Tests à livrer
- **Unitaires**: strip du slot, variation de cache.
- **Intégration (client Django)**: OFF → `/api/chat/*` → 404, ON → endpoints actifs.
- **E2E (Playwright)**: OFF → zéro script chatbot, zéro DOM `[data-chatbot]`, zéro call `/api/chat/*`.

## Critères d’acceptation
- Flag OFF: aucune balise `<script>` ou `<link>` chat, aucune route `/api/chat/*`, DOM vierge du chat, pas de requêtes chat dans la HAR.
- Flag ON: fonctionnement existant intact.

## Rollback & maintenance
- Remettre `CHATBOT_ENABLED=1` dans l’ENV → routes remontées, slot non strippé, assets inclus.
- Journaliser une ligne `atelier.feature_flags` lors du strip pour diagnostiquer vite les états.

## Pourquoi cette approche colle à ton code
- Le chat est monté comme composant Atelier; retirer le slot avant collecte supprime aussi les assets.
- L’API `/api/chat/*` est sous un namespace unique; conditionner l’include suffit à supprimer la surface.
- La variation de cache `|ff:cb` empêche qu’une page ON soit servie OFF.

## Remarques opérationnelles
- Mets `CHATBOT_ENABLED=0` dans tous tes envs tant que la conformité est en cours.
- Les logs “Too Many Requests: /api/chat/stream/” que tu as vus venaient du front; après “hard OFF”, ces lignes doivent disparaître.
