"""
Job Radar — Sistema de scoring de vagas
Score 0–100 calculado com base em skills, localização, nível e keywords.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)

# ─── Perfil do candidato ──────────────────────────────────────────────────────

CANDIDATE_SKILLS = {
    # Core (valem +3)
    "sip", "voip", "broadworks", "sbc", "wireshark",
    # Protocolos / voz (valem +2)
    "rtp", "srtp", "sip trunk", "codec", "codecs", "g.711", "g.729",
    "nat", "stun", "turn", "qos", "e1", "isdn", "ramal", "ramais",
    # Plataformas / equipamentos (valem +2)
    "ip pbx", "pabx", "pabx ip", "ura", "gateway", "khomp", "digitro",
    "leucotron", "intelbras", "grandstream", "yealink", "3cx", "asterisk",
    "freeswitch", "genesys", "avaya", "cisco", "huawei", "session border controller",
    # Comunicação unificada (valem +2)
    "unified communications", "comunicacoes unificadas", "teams", "webex",
    "zoom phone", "contact center", "call center", "ura",
    # Suporte / operação (valem +2)
    "atendimento tecnico", "suporte tecnico", "suporte nivel 2", "nivel 2",
    "troubleshooting", "analise de logs", "cdr", "ordem de servico",
    "documentacao tecnica", "noc",
    # Redes / segurança (valem +2)
    "vlan", "firewall", "vpn", "dns", "bgp", "olt", "mikrotik", "fortigate",
    "wireguard", "vmware", "rede", "redes", "network", "networking",
    "seguranca da informacao", "cybersecurity",
    # Infra / SO (valem +2)
    "windows server", "linux", "active directory", "sql server",
    # Operadoras (valem +2) — nomes ambíguos como "oi"/"claro"/"vivo" evitados
    # de propósito (palavras comuns em português, dariam falso positivo)
    "algar", "algar telecom", "tim brasil", "embratel", "operadora",
    # Cloud / crescimento (valem +2)
    "cloud", "aws", "azure", "gcp", "sd-wan",
}

CORE_SKILLS = {"sip", "voip", "broadworks", "sbc", "wireshark"}

POSITIVE_KEYWORDS = {
    # Área
    "voip", "sip", "broadworks", "sbc", "telefonia", "telefonia ip",
    "ip telephony", "unified communications", "comunicacoes unificadas",
    "pabx", "ip pbx", "ura", "call center", "contact center",
    "telecom", "telecomunicacoes", "noc", "operadora",
    # Suporte / operação
    "atendimento tecnico", "suporte tecnico", "suporte nivel 2",
    "troubleshooting", "analise de logs", "cdr", "ordem de servico",
    "missao critica", "alta disponibilidade", "incidente",
    # Protocolos / redes
    "rtp", "nat", "firewall", "vlan", "qos", "wireshark",
    # Crescimento (redes, segurança, cloud, comunicações unificadas)
    "redes", "network", "seguranca da informacao", "cybersecurity",
    "cloud", "nuvem",
    # Cargos alvo
    "analista de telecomunicacoes", "analista de telecom",
    "analista de voip", "analista sip", "administrador broadworks",
    "analista de comunicacoes unificadas", "analista noc",
    "suporte telecom", "engenheiro de voz",
    # Inglês (leitura/escrita avançadas, fala em desenvolvimento)
    "english", "inglês avançado", "ingles avancado", "fluent english",
    "advanced english", "bilingual", "inglês fluente", "ingles fluente",
    "english required", "english proficiency", "b2 english", "c1 english",
}

NEGATIVE_KEYWORDS = {
    "arquiteto", "architect", "manager", "diretor", "director",
    "cto", "vp de", "head de", "ios developer", "android developer",
    "mobile developer", "mobile engineer",
    "data scientist", "machine learning", "ml engineer",
}

SENIOR_PATTERNS = [
    r"\bs[eê]nior\b",
    r"\bsr\b\.?\s+(?:devops|engenheiro|analista)",
    r"\b8\+?\s*anos\b",
    r"\b10\+?\s*anos\b",
    r"\.net\s+s[eê]nior",
    r"java\s+s[eê]nior",
]

LOCATION_KEYWORDS_BH = {"belo horizonte", "bh", "contagem", "betim", "minas gerais", "mg"}
LOCATION_KEYWORDS_REMOTE = {"remoto", "remote", "home office", "híbrido", "hibrido", "trabalho remoto"}

# ─── Foco em remoto internacional ──────────────────────────────────────────────
# O candidato quer priorizar vagas remotas e oportunidades fora do Brasil.
# Inglês avançado para leitura/escrita — fala ainda em desenvolvimento, então
# o foco é suporte remoto assíncrono (email/chat/ticket) mais que atendimento
# telefônico constante.
OVERSEAS_KEYWORDS = {
    "worldwide", "anywhere", "global team", "distributed team",
    "remote-first", "remote first", "international team",
    "work from anywhere", "fully remote", "remote (worldwide)",
    "async", "asynchronous team", "remote, global",
}

# ─── Modo de trabalho das vagas no exterior ────────────────────────────────────
# `is_overseas` só diz "achada fora do Brasil". O filtro de remoto do LinkedIn
# não é confiável (parte das vagas vem presencial, híbrida ou remota só dentro
# de um país), então vaga no exterior só ganha crédito de remota se o TEXTO
# provar remoto, e perde se disser presencial/híbrido ou restringir a um país.
# Calibrado contra 15 vagas reais: 13 eram presenciais/travadas em país.
#
#   open           remoto + menciona Brasil/LATAM/contractor/worldwide
#   latam          remoto, achada pela busca na região Latin America
#   remote         remoto, sem restrição nem abertura explícita (elegibilidade a verificar)
#   country_locked remoto, mas só dentro de um país ("Remote, US", exige autorização)
#   onsite         presencial/híbrido, ou sem nenhuma evidência de remoto

_REMOTE_WORD_RE = re.compile(
    r"\bremot[eoa]\b|\bremotely\b|\bteletrabaj\w*|\bwork(?:ing)? from home\b|\bhome[- ]office\b"
    r"|\btrabalho remoto\b|\btrabajo remoto\b|\bwfh\b|\bwork from anywhere\b"
)
# "remote monitoring/access/support..." descreve a tarefa, não o regime de trabalho.
_REMOTE_TASK_RE = re.compile(
    r"\bremot(?:e|ely)\s+(?:monitor\w*|access\w*|troubleshoot\w*|diagnos\w*|assist\w*|sites?|hands"
    r"|locations?|devices?|servers?|data|connect\w*|login|desktop|session\w*|customers?|clients?|users?|offices?)\b"
    r"|\bremote[- ]working\s+(?:\w+\s+)?(?:solutions?|tools?|environments?|capabilit\w+|technolog\w+)\b"
)
_STRONG_REMOTE_RE = re.compile(
    r"\bfully[- ]remote\b|\b100\s?%\s*remote\b|\bremote[- ]first\b|\bremote (?:position|role|job|work)\b"
    r"|\bwork(?:ing)? remotely\b|\bwork from (?:home|anywhere)\b|\bteletrabaj\w*|\bmodalidad remota\b"
    r"|\btrabajo remoto\b|\btrabalho remoto\b|\bhome[- ]office\b|\(remote\)|[-–—]\s*remote\b"
    r"|\bremote\s*[-–—,(:]\s+\S|\blocation:?\s*remote\b|\bremote\s+(?:latam|latin|worldwide|global|brazil|anywhere)"
)
_HARD_REMOTE_RE = re.compile(
    r"\bfully[- ]remote\b|\b100\s?%\s*remote\b|\bremote[- ]first\b|\bwork from anywhere\b"
)
# Cláusulas que amarram a vaga a um escritório/cidade (vetam o remoto salvo "fully remote").
_HYBRID_OFFICE_RE = re.compile(
    r"\bhybrid\s+(?:work|working|model|role|position|schedule|environment|setup|arrangement|workspace|mode|basis|office)\b"
    r"|\b(?:work|working)\s+hybrid\b|\bhybrid\b[^.]{0,25}\b(?:days?|office)\b|\bh[ií]brid[oa]\b|\bpresencial\w*"
    r"|\bin[- ]office\b|\boffice[- ]based\b|\b(?:in|at|from)\s+(?:our|the)\s+[\w'\-, ]{0,40}\boffice\b"
    r"|\b(?:based|located)\s+in\s+(?:our|the)\s+[\w'\-, ]{0,40}\boffice\b"
    r"|\b(?:will be|is|are)\s+located\s+in\b|\brelocat\w+"
    r"|\b(?:partly|partially|part[- ]time)\b[^.]{0,30}\b(?:on[- ]?site|office|campus)\b"
    r"|\b(?:[1-9]\d?)\s?%\s*(?:home[- ]?office|remote|telework\w*|mobile work)"
)
# "on-site"/"in-person" soltos: veta só se não houver remoto explícito (remoto às vezes cita visitas).
_ONSITE_WORD_RE = re.compile(r"\bon[- ]?site\b|\bin[- ]person\b")
_COUNTRIES = (
    r"(?:us|usa|u\.s\.a?\.?|united states|canada|uk|u\.k\.|united kingdom|europe|eu|spain|españa"
    r"|germany|france|italy|poland|netherlands|ireland|australia|india|mexico|méxico|portugal"
    r"|philippines|singapore|japan)"
)
_LOCKED_RE = re.compile(
    rf"\b{_COUNTRIES}\s*[-–—,(/:]?\s*remote\b|\bremote\s*[-–—,(/:]\s*{_COUNTRIES}\b"
    rf"|\bremote\s+(?:in|within|from)\s+(?:the\s+)?{_COUNTRIES}\b"
    r"|\b(?:must|need to)\s+(?:be|live|reside|work)\s+(?:located\s+)?in\b|\bauthori[sz]ed to work in\b"
    r"|\bwork authori[sz]ation\b|\bright to work\b|(?<!no )citizenship\b|\bsecurity clearance\b"
    r"|\bresidents? of\b|\bus[- ]based\b|\bu\.?s\.? (?:only|citizens?)\b"
)
# Abertura explícita a quem mora no Brasil / contrata contractor / sem fronteira.
_OPEN_RE = re.compile(
    r"\blatam\b|\blatin america\w*|\bam[eé]rica latina\b|\bbrazil\b|\bbrasil\b"
    r"|\bremote\s*[-–—,(:]?\s*(?:worldwide|global|anywhere)\b|\b(?:worldwide|global)\s+remote\b|\bwork from anywhere\b"
    r"|\banywhere in the world\b|\bindependent contractors?\b|\bb2b\b|\bcontractor\b|\bemployer of record\b"
)


def _has_remote_evidence(t: str) -> bool:
    for m in _REMOTE_WORD_RE.finditer(t):
        if _REMOTE_TASK_RE.match(t, m.start()):
            continue
        return True
    return False


def classify_work_mode(job: dict) -> str:
    """Modo de trabalho de uma vaga do exterior (ver o bloco de comentário acima)."""
    t = _full_text(job).lower()
    strong = bool(_STRONG_REMOTE_RE.search(t))
    if not (strong or _has_remote_evidence(t)):
        return "onsite"
    hard = bool(_HARD_REMOTE_RE.search(t))
    if _HYBRID_OFFICE_RE.search(t) and not hard:
        return "onsite"
    if _ONSITE_WORD_RE.search(t) and not (strong or hard):
        return "onsite"
    if _OPEN_RE.search(t):
        return "open"
    if _LOCKED_RE.search(t):
        return "country_locked"
    if job.get("latam_ok"):
        return "latam"
    return "remote"


# (pontos de localização, bônus overseas, teto do score, limiar de alto fit)
_MODE_RULES = {
    "open":           (20, 15, None, 60),
    "latam":          (14, 10, None, 70),
    "remote":         (10, 3, 69, 70),   # sem prova de que aceita o Brasil: nunca "alto" (salvo big tech)
    "country_locked": (3, 0, 65, 70),
    "onsite":         (0, 0, 49, 70),
}

# ─── Empresas alvo (operadoras / fabricantes / plataformas de telecom) ────────
# Vagas dessas empresas recebem +15 no score e threshold mais baixo
# para alto fit (60 em vez de 70). Match normaliza (lowercase, sem acento).
TARGET_COMPANIES = {
    # Operadoras / telecom BR
    "vivo", "telefônica", "telefonica", "claro", "tim", "tim brasil", "oi",
    "nextel", "algar", "algar telecom", "embratel", "sercomtel", "brisanet",
    "desktop", "americanet", "copel telecom", "unifique", "vero internet",
    "hughes", "gvt", "cemig telecom",
    # ISPs / data centers / infra de rede
    "v.tal", "vtal", "ascenty", "equinix", "ativas data center", "diveo",
    "eletronet",
    # Fabricantes / plataformas VoIP, PABX, SBC, UC
    "khomp", "digitro", "leucotron", "intelbras", "grandstream", "yealink",
    "cisco", "avaya", "genesys", "3cx", "ringcentral", "zoom",
    "broadsoft", "huawei", "nec", "zte", "ericsson", "nokia", "microsoft",
    # CPaaS / comunicação / contact center
    "twilio", "zenvia", "movidesk", "totvs", "vonage",
    # Consultoria / integradores com forte atuação em telecom
    "ntt data", "ntt", "stefanini", "compass uol",
}

# ─── Skills prioritárias do candidato ─────────────────────────────────────────
# Áreas de crescimento declaradas pelo candidato (redes, segurança, cloud e
# comunicações unificadas). Vagas que mencionam essas skills recebem boost
# extra de +1 cada (cap +10).
PRIORITY_SKILLS = {
    "redes", "network", "networking", "seguranca da informacao",
    "cybersecurity", "cyber security", "ciberseguranca",
    "cloud", "aws", "azure", "gcp", "sd-wan", "zero trust",
    "unified communications", "comunicacoes unificadas",
}

SALARY_PATTERN = re.compile(r"r\$\s*([\d.,]+)", re.IGNORECASE)

# ─── Regex pré-compilados (evita re-compilar por job) ────────────────────────
_SENIOR_RE = [re.compile(p) for p in SENIOR_PATTERNS]
_NEGATIVE_RE = [(kw, re.compile(r"\b" + re.escape(kw) + r"\b")) for kw in NEGATIVE_KEYWORDS]
_SKILL_RE = [(skill, re.compile(r"\b" + re.escape(skill) + r"\b")) for skill in CANDIDATE_SKILLS]
_LEVEL_JR_RE = re.compile(r"\bj[uú]nior\b|\bjr\b")
_LEVEL_PL_RE = re.compile(r"\bpleno\b|\bpl\b\s+(?:devops|engenheiro|analista)")
_PRIORITY_SKILL_RE = [(s, re.compile(r"\b" + re.escape(s) + r"\b")) for s in PRIORITY_SKILLS]


# ─── Relevância do cargo (título) ─────────────────────────────────────────────
# O score por skills sozinho não segura ruído: uma vaga de "Backend Java" cita
# AWS, Docker e Python na descrição e chegava a 70. O título diz a carreira;
# por isso ele é o primeiro portão, antes de qualquer pontuação.

def _norm_title(text: str) -> str:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9+#/ ]+", " ", t)


# Fora de TI — descarta sempre (engenharia civil, adm, vendas...)
_TITLE_NON_TECH = re.compile(
    r"pavimenta|rodovi|\bcivil\b|\bobras?\b|saneamento|predial|eletric|mecanic"
    r"|\bminas\b|minera|geotecn|clinic|hospitalar|industrial|facilities"
    r"|manutencao|contab|fiscal|financeir|compras|comprador|vendas|comercia"
    r"|marketing|\bsdr\b|\bbdr\b|recursos humanos|departamento pessoal"
    r"|administrativ|secretari|eventos|juridic|logistic|frota|orcamento"
    r"|contratos?\b|planejamento|producao|processos|estagi|aprendiz"
)
# Acima do nível-alvo (5 anos de experiência)
_TITLE_TOO_SENIOR = re.compile(
    r"\b(senior|sr|staff|principal|lead|lider|tech lead|head|gerente|manager"
    r"|coordenador|coordinator|diretor|director|supervisor|master|iii)\b"
)
# Cargo claramente da área — basta sozinho
_TITLE_CORE_STRONG = re.compile(
    r"\b(voip|sip|broadworks|sbc|session border controller|telefonia ip"
    r"|ip telephony|unified communications|comunicacoes unificadas"
    r"|comunicacao unificada|ip pbx|pabx|telecomunicacoes|telecom|noc"
    r"|analista de voz|engenheir[oa] de voz|voz sobre ip)\b"
)
# Termos fortes, porém genéricos: podem aparecer em cargos de outra carreira
# de TI que só citam telecom como domínio da empresa. Sozinhos contam; ao
# lado de outra carreira, só adjacente.
_TITLE_CORE_GENERIC = re.compile(r"\b(telecom|noc|pabx)\b")
# Termos da área que sozinhos são ambíguos (aparecem em cargos de suporte geral)
_TITLE_CORE_WEAK = re.compile(
    r"\b(redes|network|networking|telefonia|suporte tecnico|nivel 2|n2)\b"
)
# Outra carreira de TI — descarta mesmo com termo fraco da área
_TITLE_OTHER_TECH = re.compile(
    r"\b(full ?stack|front ?end|back ?end|desenvolvedor|developer|programador"
    r"|software engineer|software developer|engenheir[oa] de software"
    r"|desenvolvimento|data|dados|analytics|bi|cientista|scientist"
    r"|machine learning|ml|ia|ai|artificial intelligence|inteligencia artificial"
    r"|qa|quality|qualidade|tester|salesforce|sap|servicenow|dba"
    r"|banco de dados|database|mobile|ios|android|ux|ui|produto|product"
    r"|scrum|agile)\b"
)
# Carreira vizinha (DevOps, Cloud, segurança): área de interesse futuro do
# candidato, mas ainda não é o foco atual — próxima, mas não é Telecom/VoIP.
# É classificada à parte só para o log dizer o motivo — também é rejeitada.
_TITLE_ADJACENT = re.compile(
    r"\b(devops|dev ops|sre|site reliability|kubernetes|k8s|cloud engineer"
    r"|cloud ops|cloudops|cloud operations|cloud analyst|cloud platform"
    r"|analista (de )?cloud|engenheir[oa] (de )?(cloud|nuvem)|platform engineer"
    r"|engenheir[oa] de plataforma|platform|plataforma|infraestrutura"
    r"|infrastructure|infra|seguranca da informacao|cyber ?security"
    r"|ciberseguranca|security engineer|sysadmin|system administrator"
    r"|administrador de sistemas)\b"
)


def classify_title(title: str) -> str:
    """
    Classifica o cargo pelo título:
      'core'     — Telecom / VoIP / SIP / BroadWorks / NOC / Unified Comms
      'adjacent' — carreira de interesse futuro (DevOps, Cloud, segurança)
      'senior'   — nível acima do alvo
      'off'      — fora da área
    """
    t = _norm_title(title)
    if not t.strip():
        return "off"
    if _TITLE_NON_TECH.search(t):
        return "off"
    if _TITLE_TOO_SENIOR.search(t):
        return "senior"

    other = bool(_TITLE_OTHER_TECH.search(t))
    strong = _TITLE_CORE_STRONG.search(t)
    if strong:
        generic_only = bool(_TITLE_CORE_GENERIC.fullmatch(strong.group(0)))
        if other and generic_only:
            return "adjacent"
        return "core"
    if other:
        return "off"
    if _TITLE_CORE_WEAK.search(t):
        return "core"
    if _TITLE_ADJACENT.search(t):
        return "adjacent"
    return "off"


def is_target_company(company: str) -> bool:
    """
    Verifica se o nome da empresa bate com a lista de big techs alvo.
    Normaliza (lowercase, sem pontuação) e usa substring match.
    """
    if not company or company == "N/A":
        return False
    # Normaliza: lowercase + remove pontuação/separadores extras
    norm = re.sub(r"[^\w\s]", " ", company.lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    # Match exato OU como token isolado dentro do nome
    for target in TARGET_COMPANIES:
        if target == norm or f" {target} " in f" {norm} ":
            return True
    return False


def is_obviously_rejected(text: str) -> bool:
    """
    Verifica rápido se um texto (geralmente só o título) bate em padrões de
    rejeição automática (sênior / palavra-chave negativa).
    Usado pelo scraper para pular fetch de descrições de vagas que serão
    descartadas de qualquer jeito. Evita ~30-40% das requisições.
    """
    if classify_title(text) != "core":
        return True
    text_lower = text.lower()
    for rx in _SENIOR_RE:
        if rx.search(text_lower):
            return True
    for _, rx in _NEGATIVE_RE:
        if rx.search(text_lower):
            return True
    return False

# ─── Extração de email de contato ─────────────────────────────────────────────
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_SKIP_EMAIL_LOCALS = {
    "noreply", "no-reply", "support", "contato", "info", "contact",
    "jobs", "vagas", "careers", "rh", "recrutamento", "selecao",
    "cadastro", "candidatos", "aplicacao", "apply",
}

def extract_contact_email(text: str) -> Optional[str]:
    """Retorna o primeiro email de contato humano encontrado no texto."""
    for match in _EMAIL_RE.finditer(text):
        email = match.group(0).lower()
        local = email.split("@")[0].rstrip(".")
        if local not in _SKIP_EMAIL_LOCALS and len(local) > 2:
            return email
    return None


@dataclass
class ScoreResult:
    total: int
    skills: int
    location: int
    level: int
    keywords: int
    salary: int
    skills_match: list[str]
    skills_gap: list[str]
    fit_level: str
    rejected: bool
    rejection_reason: str = ""
    contact_email: Optional[str] = None
    target_company: bool = False
    target_company_bonus: int = 0
    priority_bonus: int = 0
    priority_skills: list[str] = None
    title_bonus: int = 0
    title_class: str = ""
    is_overseas: bool = False
    overseas_bonus: int = 0
    work_mode: str = ""


def score_job(job_dict: dict) -> ScoreResult:
    text = _full_text(job_dict)
    text_lower = text.lower()

    # ── Email de contato ────────────────────────────────────────────────────
    contact_email = extract_contact_email(text)

    # ── Portão do cargo: título fora da área nem chega a ser pontuado ───────
    title_class = classify_title(job_dict.get("title", ""))
    if title_class != "core":
        motivo = {
            "senior": "Cargo acima do nível-alvo",
            "adjacent": "Carreira de interesse futuro (DevOps/Cloud/segurança), não é Telecom/VoIP",
        }.get(title_class, "Cargo fora da área (Telecom/VoIP/SIP/NOC/Unified Communications)")
        return ScoreResult(
            total=0, skills=0, location=0, level=0, keywords=0, salary=0,
            skills_match=[], skills_gap=[], fit_level="baixo", rejected=True,
            rejection_reason=motivo, contact_email=contact_email,
            title_class=title_class,
        )

    # ── Rejeição automática ─────────────────────────────────────────────────
    for rx in _SENIOR_RE:
        if rx.search(text_lower):
            return ScoreResult(
                total=0, skills=0, location=0, level=0,
                keywords=0, salary=0,
                skills_match=[], skills_gap=[],
                fit_level="baixo", rejected=True,
                rejection_reason=f"Padrão sênior detectado: {rx.pattern}",
                contact_email=contact_email,
            )

    for kw, rx in _NEGATIVE_RE:
        if rx.search(text_lower):
            return ScoreResult(
                total=0, skills=0, location=0, level=0,
                keywords=0, salary=0,
                skills_match=[], skills_gap=[],
                fit_level="baixo", rejected=True,
                rejection_reason=f"Keyword negativa: {kw}",
                contact_email=contact_email,
            )

    # ── Skills match (cap 40) ───────────────────────────────────────────────
    skills_found = []
    skills_missing = []
    for skill, rx in _SKILL_RE:
        if rx.search(text_lower):
            skills_found.append(skill)
        else:
            skills_missing.append(skill)

    skills_score = 0
    for skill in skills_found:
        skills_score += 3 if skill in CORE_SKILLS else 2
    skills_score = min(skills_score, 40)

    # ── Localização (20) ────────────────────────────────────────────────────
    # Vaga marcada is_overseas só quer dizer "achada fora do Brasil": o modo de
    # trabalho vem do texto (classify_work_mode), não da origem da busca.
    is_overseas_job = bool(job_dict.get("is_overseas"))
    loc_text = (job_dict.get("location", "") + " " + job_dict.get("description", "")).lower()
    work_mode = ""
    score_cap = None
    if is_overseas_job:
        work_mode = classify_work_mode(job_dict)
        location_score, _, score_cap, _ = _MODE_RULES[work_mode]
        is_remote = work_mode in ("open", "latam", "remote")
    else:
        is_remote = any(kw in loc_text for kw in LOCATION_KEYWORDS_REMOTE)
        location_score = 0
        if is_remote or any(kw in loc_text for kw in LOCATION_KEYWORDS_BH):
            location_score = 20
        # outra cidade presencial = 0

    # ── Nível (20) ──────────────────────────────────────────────────────────
    level_score = 10  # padrão: sem menção
    if _LEVEL_JR_RE.search(text_lower):
        level_score = 20
    elif _LEVEL_PL_RE.search(text_lower):
        level_score = 15
    # sênior já foi rejeitado acima

    # ── Keywords positivas (cap 10) ─────────────────────────────────────────
    kw_score = 0
    for kw in POSITIVE_KEYWORDS:
        if kw in text_lower:
            kw_score += 2
    kw_score = min(kw_score, 10)

    # ── Salário (10) ────────────────────────────────────────────────────────
    salary_score = 5  # não informado
    salary_text = job_dict.get("salary", "")
    if salary_text:
        values = [_parse_salary(v) for v in SALARY_PATTERN.findall(salary_text)]
        values = [v for v in values if v > 0]
        if values:
            max_val = max(values)
            if max_val >= 4000:
                salary_score = 10
            elif max_val >= 2000:
                salary_score = 5
            else:
                salary_score = 0

    # ── Boost de empresa alvo (Big Tech) ────────────────────────────────────
    company = job_dict.get("company", "")
    target_company = is_target_company(company)
    target_company_bonus = 0
    if target_company:
        target_company_bonus = 15
        # Combo Big Tech + Remoto: combinação perfeita → +5 extra
        if is_remote:
            target_company_bonus += 5

    # ── Boost de skills prioritárias (GCP) ──────────────────────────────────
    # +1 por skill prioritária encontrada na descrição (cap +10).
    # Reflete áreas onde o candidato tem ou está adquirindo expertise.
    priority_skills_found = []
    for skill, rx in _PRIORITY_SKILL_RE:
        if rx.search(text_lower):
            priority_skills_found.append(skill)
    priority_bonus = min(len(priority_skills_found), 10)

    # Cargo exatamente da área vale mais que carreira vizinha
    title_bonus = 10 if title_class == "core" else 0

    # ── Boost de remoto internacional (cap 15) ──────────────────────────────
    # Vaga do exterior: o bônus depende do modo de trabalho (aberta ao Brasil
    # vale 15, remota sem informação 3, presencial/travada em país 0);
    # vaga daqui: +3 por keyword de remoto internacional no texto.
    if is_overseas_job:
        overseas_bonus = _MODE_RULES[work_mode][1]
    else:
        overseas_kw_found = sum(1 for kw in OVERSEAS_KEYWORDS if kw in text_lower)
        overseas_bonus = min(overseas_kw_found * 3, 15)

    total = (skills_score + location_score + level_score + kw_score +
             salary_score + target_company_bonus + priority_bonus + title_bonus +
             overseas_bonus)
    total = min(total, 100)
    # Presencial/híbrida no exterior nunca passa de "baixo"; remota travada em
    # um país nunca passa de "médio" — o candidato é brasileiro, sem autorização
    # de trabalho fora.
    if score_cap is not None:
        total = min(total, score_cap)

    # Threshold mais baixo de alto fit para big tech ou vaga remota aberta ao
    # Brasil (60 vs 70) — reflete a prioridade atual do candidato.
    if is_overseas_job:
        alto_threshold = _MODE_RULES[work_mode][3]
        if target_company and alto_threshold > 60 and work_mode in ("open", "latam", "remote"):
            alto_threshold = 60
    else:
        alto_threshold = 60 if target_company else 70
    if total >= alto_threshold:
        fit_level = "alto"
    elif total >= 50:
        fit_level = "medio"
    else:
        fit_level = "baixo"

    if target_company:
        combo = " +remoto" if is_remote else ""
        log.info("🎯 Empresa alvo detectada: %s (boost +%d%s, threshold alto=60)",
                 company, target_company_bonus, combo)
    if is_overseas_job:
        log.info("🌍 Vaga no exterior [%s]: %s @ %s (boost +%d, threshold alto=%d)",
                 work_mode, job_dict.get("title", ""), company, overseas_bonus, alto_threshold)

    if contact_email:
        log.info("Email de contato detectado: %s → %s", contact_email, job_dict.get("title", ""))

    return ScoreResult(
        total=total,
        skills=skills_score,
        location=location_score,
        level=level_score,
        keywords=kw_score,
        salary=salary_score,
        skills_match=sorted(skills_found),
        skills_gap=sorted(skills_missing),
        fit_level=fit_level,
        rejected=False,
        contact_email=contact_email,
        target_company=target_company,
        target_company_bonus=target_company_bonus,
        priority_bonus=priority_bonus,
        priority_skills=sorted(priority_skills_found),
        title_bonus=title_bonus,
        title_class=title_class,
        is_overseas=is_overseas_job,
        overseas_bonus=overseas_bonus,
        work_mode=work_mode,
    )


def apply_scores(jobs: list[dict]) -> list[dict]:
    scored = []
    rejected = 0
    for job in jobs:
        result = score_job(job)
        if result.rejected:
            log.info("REJEITADO [%s]: %s @ %s — %s",
                     result.rejection_reason, job.get("title"), job.get("company"), job.get("url"))
            rejected += 1
            job["score"] = 0
            job["score_breakdown"] = {}
            job["skills_match"] = []
            job["skills_gap"] = []
            job["fit_level"] = "baixo"
            job["status"] = "arquivada"
            job["contact_email"] = result.contact_email
            job["rejected"] = True
            job["rejected_reason"] = result.rejection_reason
        else:
            log.info("Score %d [%s] — %s @ %s",
                     result.total, result.fit_level, job.get("title"), job.get("company"))
            job["score"] = result.total
            job["score_breakdown"] = {
                "skills": result.skills,
                "location": result.location,
                "level": result.level,
                "keywords": result.keywords,
                "salary": result.salary,
                "target_company": result.target_company_bonus,
                "priority_skills": result.priority_bonus,
                "title": result.title_bonus,
                "overseas": result.overseas_bonus,
            }
            job["title_class"] = result.title_class
            job["skills_match"] = result.skills_match
            job["skills_gap"] = result.skills_gap
            job["fit_level"] = result.fit_level
            job["contact_email"] = result.contact_email
            job["target_company"] = result.target_company
            job["priority_skills"] = result.priority_skills or []
            job["is_overseas"] = result.is_overseas
            job["work_mode"] = result.work_mode
            job.pop("rejected", None)
            job.pop("rejected_reason", None)
            if job.get("status") == "nova":
                pass  # mantém "nova"
        scored.append(job)

    log.info("Scoring concluído: %d processadas, %d rejeitadas", len(scored), rejected)
    return scored


def compute_stats(jobs: list[dict]) -> dict:
    total = len(jobs)
    alto = sum(1 for j in jobs if j.get("fit_level") == "alto" and j.get("status") != "arquivada")
    medio = sum(1 for j in jobs if j.get("fit_level") == "medio" and j.get("status") != "arquivada")
    baixo = sum(1 for j in jobs if j.get("fit_level") == "baixo" or j.get("status") == "arquivada")
    enviadas = sum(1 for j in jobs if j.get("status") == "enviada")
    return {
        "total": total,
        "alto_fit": alto,
        "medio_fit": medio,
        "baixo_fit": baixo,
        "enviadas": enviadas,
    }


def _full_text(job: dict) -> str:
    return " ".join([
        job.get("title", ""),
        job.get("company", ""),
        job.get("description", ""),
        job.get("location", ""),
    ])


def _parse_salary(raw: str) -> float:
    try:
        return float(raw.replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0
