#!/usr/bin/env python3
"""Write public listing build arguments and Compose settings without credentials."""
import argparse
import json
from pathlib import Path
import re

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--slug", required=True)
parser.add_argument("--name", required=True)
parser.add_argument("--blurb", required=True)
args = parser.parse_args()
if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", args.slug):
    parser.error("slug exige 2 a 64 letras minúsculas, números ou hífens")
if any("\n" in v or "\r" in v or "\x00" in v or "'" in v for v in (args.name, args.blurb)):
    parser.error("nome e descrição devem ter uma linha, sem apóstrofo")
root = Path(__file__).resolve().parents[1]
listing = {"slug": args.slug, "name": args.name, "blurb": args.blurb}
(root / "listing.json").write_text(json.dumps(listing, ensure_ascii=False, indent=2) + "\n")
(root / ".env").write_text(
    f"AGENT_ID='{args.slug}'\nAGENT_NAME='{args.name}'\nAGENT_BLURB='{args.blurb}'\n")
(root / ".env").chmod(0o600)
print(f"Configuração preparada para {args.slug}. Ainda não cadastrado no índice.")
