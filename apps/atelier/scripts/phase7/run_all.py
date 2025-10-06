"""
Exécution:
  python manage.py runscript <this_package>.run_all
"""
import importlib, pkgutil, time
ANSI={"G":"\033[92m","R":"\033[91m","B":"\033[94m","X":"\033[0m"}
def run():
    start=time.time()
    package=__name__.rsplit(".",1)[0]+".tests_scripts"
    results=[]
    for _,modname,_ in pkgutil.iter_modules(importlib.import_module(package).__path__):
        if not modname.startswith("test_"): 
            continue
        m=importlib.import_module(f"{package}.{modname}")
        if hasattr(m,"run"):
            print(f"→ Running {modname}")
            res=m.run()
            if not isinstance(res,dict):
                res={"ok":bool(res),"name":modname,"duration":0.0,"logs":[]}
            results.append(res)
    ok=sum(1 for r in results if r.get("ok"))
    print(f"Terminé: {ok}/{len(results)} OK en {round(time.time()-start,2)}s")
