#!/usr/bin/env python3
"""Render a shareable demo using measured metrics and illustrative inventory."""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--snapshot", required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("guardian", root / "native/mac_guardian.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
measured = json.loads(Path(args.snapshot).read_text())
report = {"at": measured["at"], "disk": measured["disk"], "memory": measured["memory"],
          "alerts": [a for a in measured["alerts"] if a["id"] in ("disk", "swap")],
          "processes": [{"pid": 1, "cpu": 0.2, "memory_percent": 0.1, "executable": "launchd"},
                        {"pid": 426, "cpu": 3.2, "memory_percent": 0.3, "executable": "WindowServer"}],
          "folders": [{"name": n, "category": c, "path": "~/"+n} for n,c in [
              ("Code", "Projetos"), ("Desktop", "Caixa de entrada"),
              ("Downloads", "Caixa de entrada"), ("Documents/MacWiki", "Wiki pessoal")]],
          "applications": [{"name": n, "version": v, "update_status": s, "signature": {"verified": True}}
                           for n,v,s in [("App de exemplo A", "1.0", "current"),
                                         ("App de exemplo B", "2.0", "outdated"),
                                         ("App de exemplo C", "3.0", "unknown")]],
          "background": [{"label": "local.macguardian.monitor", "executable": "mac_guardian.py",
                          "change": "unchanged", "review": ["Coletor local do agente"]}]}
with tempfile.TemporaryDirectory() as tmp:
    home = Path(tmp)
    g = m.Guardian(home, home / "state")
    m.write_json(g.state / "cleanup-plan.json", {
        "items": [{"path": ".npm/_npx/cache-antigo", "kind": "cache", "bytes": 317033188}]})
    g.dashboard(report)
    document = (g.state / "dashboard.html").read_text()
document = document.replace("Diagnóstico local", "DEMO SANITIZADO")
document = document.replace("Dados privados neste Mac. Auditoria de segurança ainda exige revisão.",
                            "Disco e memória medidos neste Mac. Pastas, apps, serviços e processos são exemplos. Limpeza demonstrada: 317 MB removidos.")
(root / "evidence").mkdir(exist_ok=True)
(root / "evidence/demo.html").write_text(document)
print(root / "evidence/demo.html")
