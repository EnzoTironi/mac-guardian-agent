#!/usr/bin/env python3
"""Capture a real, isolated file-organization round trip for visual review."""
import argparse
import html
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location("guardian", Path(__file__).parents[1] / "native/mac_guardian.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
captures = []
with tempfile.TemporaryDirectory(prefix="mac-guardian-demo-") as tmp:
    home = Path(tmp) / "home"
    home.mkdir()
    g = m.Guardian(home, Path(tmp) / "state")
    g.policy.update(auto_updates=False, auto_projects=False, backup_repo="")
    fixtures = {"Downloads/fatura.pdf": b"Example document A", "Desktop/fatura.pdf": b"Example document B",
                "Desktop/ideias.md": "# Planejamento da viagem - Itália".encode(), "Downloads/Viagens/Italia/roteiro.pdf": b"Example itinerary",
                "Downloads/apresentacao.pptx": b"Example presentation", "Downloads/Projeto/README.md": b"Project paths stay stable",
                "Downloads/Projeto/package.json": b"{}", "Downloads/em-uso-recente.pdf": b"Recent file stays in place"}
    for name, content in fixtures.items():
        p = home / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        if "em-uso-recente" not in name:
            os.utime(p, (time.time() - 3 * m.DAY,) * 2)
    m.write_json(g.state / "snapshot.json", {"full_checked_at": m.now(), "applications": [], "updates": {}, "security": {}})
    def capture(title, detail):
        files = [p.relative_to(home).as_posix() for p in sorted(home.rglob("*"))
                 if p.is_file() and not p.is_symlink() and p.relative_to(home).parts[0] != "Library"]
        captures.append({"title": title, "detail": detail, "files": files})
    capture("Antes da rotina", "Downloads e Mesa contêm arquivos de exemplo. Documents está excluída.")
    result = g.maintain()
    organization = next(s["result"] for s in result["stages"] if s["name"] == "organization")
    assert len(organization["items"]) == 5
    assert all(m.digest(i["destination"]) == i["sha256"] for i in organization["items"])
    assert (home / "Downloads/Projeto/README.md").exists()
    assert (home / "Downloads/em-uso-recente.pdf").exists()
    assert any(Path(i["destination"]).name == "planejamento-da-viagem-italia.md" for i in organization["items"])
    capture("Arquivos organizados e renomeados", "5 arquivos na wiki local; nome da nota veio do conteúdo. Hashes, assuntos, nomes iguais e projeto preservados.")
    undo = g.undo(organization["transaction"])
    assert undo["restored"] == 5
    assert all((home / p).read_bytes() == data for p, data in fixtures.items())
    capture("Movimentos desfeitos", "5 arquivos restaurados aos locais originais, com conteúdo idêntico.")
for i, item in enumerate(captures):
    links = " ".join(f'<a href="step-{j+1}.html">{j+1}. {html.escape(c["title"])}</a>' for j, c in enumerate(captures))
    body = f'''<!doctype html><meta charset="utf-8"><title>Mac Guardian — teste da wiki</title>
<style>body{{background:#101c25;color:#eef5f5;font:18px system-ui;margin:40px auto;max-width:1080px}}h1{{font-size:38px;margin-bottom:12px}}p{{color:#bed0d6}}nav{{display:flex;gap:28px;margin:28px 0}}a{{color:#8bdac8}}pre{{background:#172a36;border:1px solid #42616c;border-radius:12px;padding:22px;font:17px/1.55 monospace}}footer{{font-size:15px;color:#a6b8c3}}</style>
<p>MAC GUARDIAN · v{m.VERSION} · RESULTADOS DE TESTE EXECUTADO</p><h1>{html.escape(item["title"])}</h1>
<p>{html.escape(item["detail"])}</p><nav>{links}</nav><pre>{html.escape(chr(10).join(item["files"]))}</pre>
<footer>Arquivos sintéticos em pasta temporária. Organização e undo executados pelo helper real.<br>Sem atualizações de apps, uploads de dados ou acesso a documentos pessoais.</footer>'''
    m.private_text(args.output / f"step-{i+1}.html", body)
m.write_json(args.output / "proof.json", {"version": m.VERSION, "moved": 5, "restored": 5,
                                           "hashes_verified": True, "captures": captures})
print(json.dumps({"pages": str(args.output.resolve()), "moved": 5, "restored": 5, "hashes_verified": True}))
