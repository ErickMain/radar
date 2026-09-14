"""
Job Radar — Fila de candidaturas manuais (LOCAL — não roda no GitHub Actions)

O robô encontra e qualifica vagas sozinho, mas a candidatura de verdade no
LinkedIn (ou no site da empresa) continua sendo você que faz — esse script
só organiza isso: abre cada vaga elegível numa aba de um navegador de
verdade, mostra a carta já gerada (se tiver), e depois que você aplicar
manualmente, registra o status e sincroniza de volta pro dashboard.

Não mexe no formulário de "Candidatura simplificada" — só abre a vaga e
espera você. Isso é proposital: preencher/quase-enviar formulário por
script é mais "robótico" aos olhos do LinkedIn (risco de restrição de
conta) e os seletores deles mudam com frequência.

Por que conecta no Chrome de verdade em vez de abrir um Chromium próprio:
o Playwright `launch()` marca o navegador como controlado por automação
(navigator.webdriver=true, infobar "Chrome is being controlled by
automated test software"), e tanto o LinkedIn quanto o login do Google
bloqueiam login nesse tipo de sessão. Solução: o script abre o chrome.exe
de verdade como um processo normal (não via API do Playwright) com um
perfil próprio e a porta de depuração remota, e só DEPOIS se conecta nele
via CDP — o login acontece 100% humano, numa janela que nunca foi marcada
como automatizada.

Setup (uma vez):
    .venv\\Scripts\\pip install playwright
    .venv\\Scripts\\python -m playwright install chromium

Uso:
    .venv\\Scripts\\python scripts\\apply_local.py

Na primeira execução abre uma janela do Chrome (perfil próprio, separado
do seu Chrome do dia a dia — fica em .chrome-automation-profile/, fora do
git) pedindo login no LinkedIn. Faça o login normalmente; a sessão fica
salva e é reaproveitada nas próximas vezes.
"""

import json
import subprocess
import sys
import time
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
PROFILE_DIR = ROOT / ".chrome-automation-profile"
DONE_STATUSES = {"enviada", "rejeitada", "arquivada"}
CDP_PORT = 9222

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    str(Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe"),
]


def find_chrome() -> str:
    for path in CHROME_CANDIDATES:
        if Path(path).exists():
            return path
    print(
        "Não encontrei o Chrome nos caminhos padrão do Windows. "
        "Se estiver instalado em outro lugar, edite CHROME_CANDIDATES no topo "
        "de scripts/apply_local.py com o caminho certo."
    )
    sys.exit(1)


def connect_browser(p):
    """
    Conecta num Chrome real via CDP. Se não tiver um escutando na porta,
    sobe um novo (processo normal, sem marca de automação) com perfil
    próprio e espera ficar pronto.
    """
    try:
        return p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
    except Exception:
        pass

    chrome_path = find_chrome()
    PROFILE_DIR.mkdir(exist_ok=True)
    print("Abrindo o Chrome (perfil separado, só pra essa ferramenta)...")
    subprocess.Popen([
        chrome_path,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
    ])

    for _ in range(20):
        time.sleep(0.5)
        try:
            return p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
        except Exception:
            continue

    print("Não consegui conectar no Chrome depois de abrir. Tente rodar de novo.")
    sys.exit(1)


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

    changed = False
    with sync_playwright() as p:
        browser = connect_browser(p)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()

        try:
            first = True
            for i, job in enumerate(queue, 1):
                if first:
                    print(
                        "\nSe essa for a primeira vez, faça login no LinkedIn na "
                        "janela do Chrome que abriu antes de continuar."
                    )
                    input("Pressione ENTER quando estiver logado (ou já estava): ")
                    first = False

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
            page.close()
            # Não fecha o browser/context: é o Chrome real do usuário, ele
            # decide quando fechar a janela.

    if changed:
        sync_and_offer_push(data)
    else:
        print("\nNada mudou, nada pra salvar.")


if __name__ == "__main__":
    main()
