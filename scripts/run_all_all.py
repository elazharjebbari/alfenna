"""
Exécution:
  DJANGO_SETTINGS_MODULE=alfenna.settings.dev \n  python manage.py runscript scripts.run_all_all
"""
import importlib, time
RUN_ALL_TARGETS = [
    # Atelier
    "apps.atelier.scripts.components.run_all",
    "apps.atelier.scripts.formfront.run_all",
    "apps.atelier.scripts.images.run_all",
    "apps.atelier.scripts.phase3.run_all",
    "apps.atelier.scripts.phase6.run_all",
    "apps.atelier.scripts.phase7.run_all",
    "apps.atelier.scripts.phase8.run_all",
    "apps.atelier.scripts.suite.run_all",
    # Flowforms
    "apps.flowforms.scripts.run_flowforms_all",
    # Accounts (suite)
    "apps.accounts.scripts.suite.run_all",
    # Billing (suite)
    "apps.billing.scripts.suite.run_all",
    # Catalog (suite)
    "apps.catalog.scripts.suite.run_all",
    # Content (gating)
    "apps.content.scripts.gating.run_all",
    # Leads (suite)
    "apps.leads.scripts.suite.run_all",
    # Learning (suite)
    "apps.learning.scripts.suite.run_all",
    # Marketing (suite)
    "apps.marketing.scripts.suite.run_all",
]

def run():
    start=time.time()
    overall=[]
    print("\n=== Orchestrateur global — run_all_all ===")
    for dotted in RUN_ALL_TARGETS:
        print(f"\n→ Lancement: {dotted}")
        try:
            mod=importlib.import_module(dotted)
            if hasattr(mod,"run"):
                mod.run()
                overall.append((dotted,True,None))
            else:
                overall.append((dotted,False,"no run()"))
        except Exception as e:
            overall.append((dotted,False,str(e)))
    print("\n=== Résumé global ===")
    ok=0
    for dotted, status, err in overall:
        print(f"- {dotted} : {'OK' if status else 'ECHEC'}" + (f" ({err})" if err else ""))
        if status: ok+=1
    print(f"\nTotal OK: {ok}/{len(overall)}  | Durée: {round(time.time()-start,2)}s")
