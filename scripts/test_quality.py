"""
Testes de qualidade dos dados: portao de cargo, diretorio de recruiters,
convite de conexao e dedup contra vagas arquivadas.
Rodar: python scripts/test_quality.py   (sem rede, sem API)
"""
import json
import logging
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
logging.disable(logging.INFO)

import letter_gen
import recruiters
import scraper
from scorer import classify_title, score_job

FALHAS = []


def check(nome, cond, detalhe=""):
    print(("  ok    " if cond else "  FALHA ") + nome + (f"  ({detalhe})" if detalhe and not cond else ""))
    if not cond:
        FALHAS.append(nome)


print("[portao de cargo]")
casos = {
    "Analista de Telecomunicações": "core",
    "Analista SIP Pleno": "core",
    "Administrador BroadWorks": "core",
    "Analista NOC (Remote Work)": "core",
    "Analista de Telecom Junior": "core",
    "Analista de Suporte Telecom": "core",
    "DevOps Engineer": "adjacent",
    "Cloud Engineer": "adjacent",
    "Staff Software Engineer - Backend Java": "senior",
    "Analista de Telecomunicações Sr": "senior",
    "Cyber Security Junior": "adjacent",
    "Data Engineer (AWS)": "off",
    "Desenvolvedor Fullstack Node e React": "off",
    "Engenheiro Civil Especialista - Infraestrutura Rodoviaria": "off",
    "Analista Fiscal": "off",
    "Analista de Sistemas": "off",
}
for titulo, esperado in casos.items():
    got = classify_title(titulo)
    check(f"{titulo!r} -> {esperado}", got == esperado, f"veio {got}")

print("[score_job]")
base = {"company": "Acme", "location": "Remoto",
        "description": "SIP VoIP BroadWorks RTP SBC Wireshark troubleshooting analise de logs"}
r = score_job(dict(base, title="Staff Software Engineer - Backend Java"))
check("backend java com stack telecom na descricao e rejeitada", r.rejected)
r = score_job(dict(base, title="Analista de Telecomunicações"))
check("telecom aceita e ganha bonus de cargo", (not r.rejected) and r.title_bonus == 10)
r = score_job(dict(base, title="Cloud Engineer - Selecao em Andamento"))
check("carreira de interesse futuro (cloud) e rejeitada", r.rejected)
r = score_job(dict(base, title="Analista de Telecomunicações - Jr"))
check("telecom jr aceita", not r.rejected)

print("[vagas no exterior: modo de trabalho]")
ext = {"title": "NOC Engineer", "company": "Acme Corp", "location": "Berlim, Alemanha", "is_overseas": True}
skills = "SIP VoIP BroadWorks RTP SBC Wireshark troubleshooting. "


def ext_job(desc, **kw):
    return score_job(dict(ext, description=skills + desc, **kw))


r = ext_job("This is a fully remote role open to candidates in Brazil and LATAM, as an independent contractor.")
check("remota que cita Brasil/contractor -> open e pode ser alto", r.work_mode == "open" and r.fit_level == "alto",
      f"{r.work_mode} {r.total} {r.fit_level}")
r = ext_job("Work onsite at our data center in Berlin, 5 days a week.")
check("presencial no exterior -> onsite, nunca passa de baixo", r.work_mode == "onsite" and r.fit_level == "baixo" and r.total <= 49,
      f"{r.work_mode} {r.total}")
r = ext_job("We offer a hybrid working model with 3 days in the office.")
check("hibrida no exterior -> onsite", r.work_mode == "onsite")
r = ext_job("Remote monitoring of customer sites from our NOC, based in the Berlin office.")
check("'remote monitoring' descreve a tarefa, nao o regime", r.work_mode == "onsite", r.work_mode)
r = ext_job("Location: Remote, US. Must be authorized to work in the United States.")
check("'Remote, US' -> country_locked, no maximo medio", r.work_mode == "country_locked" and r.total <= 65 and r.fit_level != "alto",
      f"{r.work_mode} {r.total}")
r = ext_job("Fully remote position. Hiring in Canada only.", location="Canada - Remote")
check("'Canada - Remote' -> country_locked", r.work_mode == "country_locked", r.work_mode)
r = ext_job("Esta posicao e em modalidade teletrabajo, horario estandar.")
check("remota calada sobre elegibilidade -> remote, nunca alto", r.work_mode == "remote" and r.fit_level != "alto",
      f"{r.work_mode} {r.total} {r.fit_level}")
r = ext_job("Join our remote-first team.", latam_ok=True)
check("remote-first achada na busca Latin America -> open/latam", r.work_mode in ("open", "latam"), r.work_mode)
r = ext_job("Remote position for the LATAM region.")
check("texto que cita LATAM -> open", r.work_mode == "open", r.work_mode)
r = ext_job("We offer 40% home-office and a modern campus.")
check("'40% home-office' e beneficio de vaga presencial -> onsite", r.work_mode == "onsite", r.work_mode)
r = ext_job("Work partially at our campus and remotely.")
check("'partially at our campus and remotely' -> onsite", r.work_mode == "onsite", r.work_mode)
r = ext_job("Our solutions include remote-working voice solutions for clients.")
check("'remote-working voice solutions' e produto, nao regime", r.work_mode == "onsite", r.work_mode)
r = ext_job("This is a fully remote role. Must be able to work rotating shifts.")
check("turno rotativo nao torna a vaga presencial", r.work_mode != "onsite", r.work_mode)
loc = score_job({"title": "Analista NOC", "company": "Acme", "location": "Remoto",
                 "description": skills, "is_overseas": False})
check("vaga do Brasil nao recebe work_mode", loc.work_mode == "" and loc.location == 20)

print("[diretorio de recruiters]")
tmp = Path(tempfile.mkdtemp())
recruiters.RECRUITERS_FILE = tmp / "recruiters.json"
now = datetime.now(timezone.utc).isoformat()
velho = {"id": "old", "name": "Antigo", "profile_url": "https://br.linkedin.com/in/antigo",
         "headline": "Tech Recruiter", "is_recruiter": True, "country": "BR", "companies": ["X"],
         "jobs": [{"id": "v0", "title": "Especialista de Desenvolvimento I", "score": 46}],
         "first_seen": now, "last_seen": now, "message": None}
recruiters.save_recruiters({"recruiters": [velho], "last_updated": now})


def vaga(i, titulo, score, rec=None, empresa="Dexian"):
    return {"id": i, "title": titulo, "company": empresa, "url": "u" + i, "score": score,
            "fit_level": "alto", "location": "Remoto", "found_at": now, "recruiter": rec}


ana = {"name": "Ana Souza", "profile_url": "https://br.linkedin.com/in/ana-souza/pt",
       "headline": "Tech Recruiter | Talent Acquisition"}
d = recruiters.merge_jobs_into_directory([
    vaga("a", "Analista de Telecomunicações", 72, ana),
    vaga("b", "Desenvolvedor Fullstack", 80, {"name": "Bia", "profile_url": "https://br.linkedin.com/in/bia",
                                              "headline": "Recruiter"}),
    vaga("c", "Analista NOC Pleno", 66),               # sem recruiter -> inferida pela empresa
    vaga("d", "Analista SIP", 50),                     # abaixo do score minimo
])
nomes = {x["name"]: x for x in d["recruiters"]}
check("recruiter antigo (score 46) podado pelo criterio atual", "Antigo" not in nomes)
check("recruiter de vaga fora da area nao entra", "Bia" not in nomes)
check("recruiter de vaga Telecom entra", "Ana Souza" in nomes)
ana_d = nomes.get("Ana Souza", {})
check("vaga sem recruiter da mesma empresa foi inferida",
      any(j.get("inferred") for j in ana_d.get("jobs", [])))
check("vaga com score < 60 nao foi associada",
      all(j["id"] != "d" for j in ana_d.get("jobs", [])))
check("prioridade calculada", ana_d.get("priority", 0) >= 70, f"prioridade={ana_d.get('priority')}")

print("[convite de conexao]")
longo = {"name": "Maria Aparecida da Silva", "headline": "Recruiter",
         "jobs": [{"title": "Engenheiro(a) de Plataforma Cloud Pleno com foco em Kubernetes e Observabilidade "
                            "para squad de pagamentos", "company": "Uma Empresa de Nome Bastante Comprido S.A.",
                   "score": 80}]}
fb = letter_gen._fallback_outreach(longo)
check("convite do fallback cabe em 300 caracteres", len(fb["invite_note"]) <= 300,
      f"{len(fb['invite_note'])} chars")
check("mensagem de follow-up gerada", len(fb["message"]) > 50)
check("_fit respeita o limite", len(letter_gen._fit("palavra " * 80, 300)) <= 300)

print("[dedup contra arquivadas]")
scraper.DATA_DIR = tmp
(tmp / "archive.json").write_text(json.dumps({"jobs": [{"id": "x1", "title": "DevOps", "company": "Y"}]}),
                                  encoding="utf-8")
arq = scraper._load_archived_jobs()
check("archive.json lido para o dedup", [j["id"] for j in arq] == ["x1"])

print("[vaga aberta x fechada]")
from scraper import interpret_job_page
futuro = (datetime.now(timezone.utc) + timedelta(days=20)).isoformat()
passado = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
aberta_html = '<script>{"validThrough": "%s"}</script>' % futuro
check("LinkedIn 404 = fechada", interpret_job_page("LinkedIn", 404, "u", "")[0] is False)
check("LinkedIn redirecionou para a empresa = fechada",
      interpret_job_page("LinkedIn", 200, "https://br.linkedin.com/jobs/acme-vagas", aberta_html)[0] is False)
check("LinkedIn aberta traz o prazo",
      interpret_job_page("LinkedIn", 200, "https://br.linkedin.com/jobs/view/x-1", aberta_html) == (True, futuro))
check("prazo vencido = fechada",
      interpret_job_page("LinkedIn", 200, "https://br.linkedin.com/jobs/view/x-1",
                         '"validThrough": "%s"' % passado)[0] is False)
check("429 = incerto (nao remove)", interpret_job_page("LinkedIn", 429, "u", "")[0] is None)
check("aviso 'no longer accepting' = fechada",
      interpret_job_page("Vagas.com", 200, "u", "No longer accepting applications")[0] is False)

print("[arquivamento]")
import main
vinte_dias = (datetime.now(timezone.utc) - timedelta(days=20)).isoformat()
noventa_dias = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
ativos, arq = main._split_for_archive([
    {"id": "a", "found_at": vinte_dias, "verified_at": now},   # antiga, mas aberta
    {"id": "b", "found_at": now, "closed": True},              # fechou
    {"id": "c", "found_at": now, "valid_through": passado},    # prazo passou
    {"id": "d", "found_at": noventa_dias},                     # sem confirmacao
])
check("vaga antiga e aberta continua no banco", [j["id"] for j in ativos] == ["a"])
check("fechada/prazo -> closed, sem confirmacao -> max_age",
      {j["id"]: j["archive_reason"] for j in arq} == {"b": "closed", "c": "closed", "d": "max_age"})

print("[logo da empresa]")
from bs4 import BeautifulSoup
from scraper import _card_logo, _extract_company_logo
ld = ('<script type="application/ld+json">{"hiringOrganization":{"@type":"Organization",'
      '"name":"Acme","logo":"https://media.licdn.com/dms/image/v2/X/company-logo_200_200/a?e=1&amp;t=z"}}</script>')
check("logo lido do JSON-LD da vaga",
      _extract_company_logo(ld) == "https://media.licdn.com/dms/image/v2/X/company-logo_200_200/a?e=1&t=z")
li = BeautifulSoup('<li><img data-delayed-url="https://media.licdn.com/dms/image/v2/Y/company-logo_100_100/q"></li>',
                   "html.parser").li
check("logo lido do card da busca", _card_logo(li) == "https://media.licdn.com/dms/image/v2/Y/company-logo_100_100/q")
check("pagina sem logo -> None", _extract_company_logo("<html></html>") is None)

print()
if FALHAS:
    print(f"{len(FALHAS)} falha(s): {FALHAS}")
    sys.exit(1)
print("todos os testes passaram")
