"""
Job Radar — Fila de candidaturas manuais (LOCAL — não roda no GitHub Actions)

O robô encontra e qualifica vagas sozinho, mas a candidatura de verdade no
LinkedIn (ou no site da empresa) continua sendo você que faz — esse script
só organiza isso: abre cada vaga elegível numa aba de um navegador de
verdade, usando sua própria sessão já logada no LinkedIn, mostra a carta
já gerada (se tiver), e depois que você aplicar manualmente, registra o
status e sincroniza de volta pro dashboard.

Não mexe no formulário de "Candidatura simplificada" — só abre a vaga e
espera você. Isso é proposital: preencher/quase-enviar formulário por
script é mais "robótico" aos olhos do LinkedIn (risco de restrição de
conta) e os seletores deles mudam com frequência.

Setup (uma vez):
    .venv\\Scripts\\pip install playwright
    .venv\\Scripts\\python -m playwright install chromium

Uso:
    .venv\\Scripts\\python scripts\\apply_local.py

Na primeira execução abre um Chromium visível e pede pra você logar no
LinkedIn manualmente ali dentro — a sessão fica salva em
.playwright-profile/ (fora do git, ver .gitignore) e é reaproveitada nas
próximas vezes, sem precisar logar de novo.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from scraper import load_existing_jobs, save_jobs, BLACKLIST_FILE  # noqa: E402

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(
        "Playwright não instalado. Rode:\n"
        "  .venv\\Scripts\\pip install playwright\n"
        "  .venv\\Scripts\\python -m playwright install chromium"
    )
    sys.exit(1)

ROOT = Path(__file__).parent.parent
PROFILE_DIR = ROOT / ".playwright-profile"
DONE_STATUSES = {"enviada", "rejeitada", "arquivada"}


def eligible_jobs(jobs: list[dict]) -> list[dict]:
    """Vagas do LinkedIn, alto/médio fit, ainda sem decisão tomada."""
    elig = [
        j for j in jobs
        if j.get("source") == "LinkedIn"
        and j.get("fit_level") in ("alto", "medio")
        and j.get("status") not in DONE_STATUSES
    ]
    elig.sort(key=lambda j: j.get("score", 0), reverse=True)
    return elig


def print_job(job: dict, idx: int, total: int) -> None:
    print("\n" + "=" * 70)
    tag = "  🌍 remoto internacional" if job.get("is_overseas") else ""
    print(f"[{idx}/{total}] {job.get('title')} — {job.get('company')}{tag}")
    print(f"Score: {job.get('score')}/100 ({(job.get('fit_level') or '').upper()} FIT)")
    print(f"Local: {job.get('location', 'N/A')}")
    print(f"URL:   {job.get('url')}")
    letter = job.get("cover_letter")
    if letter:
        print("\n--- Carta gerada pro Radar (pode reaproveitar ou ajustar) ---")
        print(letter)
    else:
        print("\n(sem carta salva ainda pra essa vaga — confira os requisitos na própria página)")
    print("=" * 70)


def add_to_blacklist(job_id: str) -> None:
    ids = set()
    if BLACKLIST_FILE.exists():
        try:
            ids = set(json.loads(BLACKLIST_FILE.read_text(encoding="utf-8")).get("ids", []))
        except (json.JSONDecodeError, OSError):
            pass
    ids.add(job_id)
    BLACKLIST_FILE.write_text(
        json.dumps({"ids": sorted(ids)}, ensure_ascii=False, indent=2), encoding="utf-8",
    )


def sync_and_offer_push(data: dict) -> None:
    save_jobs(data)
    docs_copy = ROOT / "docs" / "data" / "jobs.json"
    docs_copy.parent.mkdir(parents=True, exist_ok=True)
    docs_copy.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    docs_blacklist = ROOT / "docs" / "data" / "blacklist.json"
    if BLACKLIST_FILE.exists():
        docs_blacklist.write_text(BLACKLIST_FILE.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"\nSalvo em data/jobs.json e {docs_copy.relative_to(ROOT)}.")
    resp = input("Commitar e enviar pro GitHub agora, pra o dashboard refletir? [s/N]: ").strip().lower()
    if resp != "s":
        print("Ok — os arquivos ficaram modificados localmente, commit quando quiser.")
        return
    try:
        subprocess.run(
            ["git", "add", "data/jobs.json", "docs/data/jobs.json",
             "data/blacklist.json", "docs/data/blacklist.json"],
            cwd=ROOT, check=True,
        )
        subprocess.run(
            ["git", "commit", "-m", "chore: candidaturas manuais via apply_local.py"],
            cwd=ROOT, check=True,
        )
        subprocess.run(["git", "push"], cwd=ROOT, check=True)
        print("Enviado pro GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"Falha no git ({e}) — resolva manualmente, os dados locais já estão salvos.")


def main() -> None:
    data = load_existing_jobs()
    jobs = data.get("jobs", [])
    queue = eligible_jobs(jobs)

    if not queue:
        print("Nenhuma vaga pendente (LinkedIn, alto/médio fit, ainda sem decisão).")
        return

    print(f"{len(queue)} vaga(s) na fila.")
    print("Cada uma abre numa aba — aplique manualmente do jeito que sempre fez,")
    print("depois volte aqui pra registrar.\n")

    PROFILE_DIR.mkdir(exist_ok=True)
    changed = False
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(PROFILE_DIR), headless=False, viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            for i, job in enumerate(queue, 1):
                print_job(job, i, len(queue))
                page.goto(job["url"], wait_until="domcontentloaded")

                while True:
                    resp = input(
                        "\n[s] apliquei  [n] pular por agora  "
                        "[b] nunca mais mostrar essa  [q] parar por aqui: "
                    ).strip().lower()
                    if resp == "s":
                        job["status"] = "enviada"
                        job["applied_at"] = datetime.now(timezone.utc).isoformat()
                        job["application_method"] = "manual_browser"
                        changed = True
                        break
                    if resp == "n":
                        break
                    if resp == "b":
                        job["status"] = "rejeitada"
                        add_to_blacklist(job["id"])
                        changed = True
                        break
                    if resp == "q":
                        raise KeyboardInterrupt
                    print("Opção inválida.")
        except KeyboardInterrupt:
            print("\nParando por aqui.")
        finally:
            context.close()

    if changed:
        sync_and_offer_push(data)
    else:
        print("\nNada mudou, nada pra salvar.")


if __name__ == "__main__":
    main()
