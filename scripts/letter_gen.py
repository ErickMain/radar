"""
Job Radar — Geração de carta de apresentação via Groq (gratuito)
Modelo: openai/gpt-oss-120b — os llama-3.x saíram do plano gratuito da Groq
em 2026-09 (llama-3.3-70b-versatile virou 404 "model_not_found" pra quem
não tem acesso enterprise); os modelos que sobraram no free tier são
groq/compound(-mini), openai/gpt-oss-120b/20b e qwen3.6/3.8-27b.
"""

import json
import logging
import os

from groq import Groq

log = logging.getLogger(__name__)

# Perfil do candidato — base factual usada nos prompts.
# Mantenha fiel ao currículo: o modelo não deve inventar experiência.
CANDIDATE_PROFILE = """Erick Moreira — Analista de Telecomunicações, 5 anos de experiência.
Belo Horizonte/MG.

Atuação atual — Método Telecom (desde jun/2021), Telecommunications Analyst:
- Suporte especializado em telefonia IP e VoIP, com administração de ambientes
  BroadWorks.
- Análise de protocolos SIP e RTP; troubleshooting de SBCs (Session Border
  Controllers).
- Provisionamento de ramais e dispositivos IP; configuração de telefones IP e ATAs.
- Tratativas técnicas diretas com operadoras como Oi, Algar e TIP.
- Análise de CDRs e logs SIP; captura e interpretação de tráfego com Wireshark.
- Diagnóstico de problemas de áudio, registro SIP, NAT, firewall e codecs.
- Atendimento técnico de incidentes críticos e gestão de Ordens de Serviço em
  ambientes de missão crítica.
- Elaboração de documentação técnica e procedimentos operacionais.

Stack: SIP, RTP, BroadWorks, SBC, VoIP, IP PBX, Wireshark, Windows Server,
análise de logs, CDR, NAT/firewall/codecs, atendimento técnico nível 2.

Interesse em expandir atuação para redes, segurança da informação, cloud e
comunicações unificadas."""

SYSTEM_PROMPT = """Você escreve cartas de apresentação em nome de Erick Moreira.

PERFIL DO CANDIDATO (use só o que está aqui, nunca invente experiência):
""" + CANDIDATE_PROFILE + """

Regras obrigatórias:
- Tom direto e técnico, sem exageros ou adjetivos vazios
- Máximo 4 parágrafos curtos (não mais de 5 linhas cada)
- Não começar com "Prezados" ou frases genéricas
- Destacar 2-3 pontos do perfil que casam com a vaga, preferindo
  resultados concretos (ex: troubleshooting de SBCs em ambiente de missão
  crítica, tratativas técnicas diretas com operadoras, análise de logs
  SIP/CDR com Wireshark)
- Nunca citar tecnologia ou experiência que não esteja no perfil acima
- PROIBIDO inventar números: nenhum percentual, métrica de uptime/SLA,
  redução de tempo, quantidade de incidentes ou qualquer estatística de
  performance. O perfil acima não tem números de resultado — se quiser
  citar impacto, descreva a atividade em si (ex: "troubleshooting de SBCs
  em ambiente de missão crítica"), nunca invente um número para ela
- Finalizar com disponibilidade para entrevista
- Escrever em português brasileiro formal-técnico"""

# Versão em inglês — usada para vagas remotas internacionais (is_overseas).
# Mesmos fatos, sem inventar nada; inclui o nível real de inglês para não
# criar expectativa maior do que a fala atual do candidato sustenta.
CANDIDATE_PROFILE_EN = """Erick Moreira — Telecommunications Analyst, 5 years of experience.
Based in Belo Horizonte, Brazil. Open to remote work.

Current role — Método Telecom (since Jun/2021), Telecommunications Analyst:
- Specialized support for IP telephony and VoIP, administering BroadWorks
  environments.
- SIP and RTP protocol analysis; SBC (Session Border Controller) troubleshooting.
- Extension/IP device provisioning; IP phone and ATA configuration.
- Direct technical dealings with carriers such as Oi, Algar and TIP.
- CDR and SIP log analysis; packet capture and interpretation with Wireshark.
- Diagnosing audio issues, SIP registration, NAT, firewall and codec problems.
- Critical incident handling and service ticket management in mission-critical
  environments.
- Writing technical documentation and operational procedures.

Stack: SIP, RTP, BroadWorks, SBC, VoIP, IP PBX, Wireshark, Windows Server,
log analysis, CDR, NAT/firewall/codecs, tier-2 technical support.

English level: advanced reading and writing; spoken English is currently
improving. Comfortable with async, written communication (email/chat/tickets).

Interested in growing into networking, information security, cloud and
unified communications."""

SYSTEM_PROMPT_EN = """You write cover letters on behalf of Erick Moreira.

CANDIDATE PROFILE (use only what's here, never invent experience):
""" + CANDIDATE_PROFILE_EN + """

Mandatory rules:
- Direct, technical tone, no empty adjectives or exaggeration
- Maximum 4 short paragraphs (no more than 5 lines each)
- Don't open with "Dear Sir/Madam" or generic phrases
- Highlight 2-3 points from the profile that match the job, preferring
  concrete facts (e.g. SBC troubleshooting in mission-critical environments,
  direct technical dealings with carriers, SIP/CDR log analysis with
  Wireshark)
- Never claim a technology, experience, or spoken-English fluency level
  that isn't in the profile above — the profile says reading/writing are
  advanced and speaking is still improving; don't overstate that
- DO NOT invent numbers: no percentages, uptime/SLA metrics, time
  reductions, incident counts, or any performance statistic. The profile
  above has no result numbers — if you want to convey impact, describe
  the activity itself (e.g. "SBC troubleshooting in mission-critical
  environments"), never make up a number for it
- End with availability for an interview
- Write in professional, technical English"""

GROQ_MODEL = "openai/gpt-oss-120b"


def generate_cover_letter(job: dict) -> str:
    """Gera carta personalizada para a vaga. Retorna texto da carta."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY não configurada")

    client = Groq(api_key=api_key)

    overseas = bool(job.get("is_overseas"))
    title = job.get("title", "")
    company = job.get("company", "")
    description = job.get("description", "")[:1500]
    skills_match = job.get("skills_match", [])
    skills_gap = job.get("skills_gap", [])

    if overseas:
        system_prompt = SYSTEM_PROMPT_EN
        user_prompt = f"""Job: {title} at {company}

Job description (excerpt):
{description}

Skills from the job Erick has: {', '.join(skills_match[:10]) if skills_match else 'SIP, VoIP, BroadWorks'}
Skills from the job Erick doesn't have: {', '.join(skills_gap[:5]) if skills_gap else 'none relevant'}

Write a personalized, concise cover letter for Erick to apply to this job. \
Focus on the matching skills and the value he can bring to the company."""
    else:
        system_prompt = SYSTEM_PROMPT
        user_prompt = f"""Vaga: {title} na {company}

Descrição da vaga (resumida):
{description}

Skills da vaga que Erick possui: {', '.join(skills_match[:10]) if skills_match else 'SIP, VoIP, BroadWorks'}
Skills da vaga que Erick não possui: {', '.join(skills_gap[:5]) if skills_gap else 'nenhuma relevante'}

Escreva uma carta de apresentação personalizada e objetiva para Erick se candidatar \
a esta vaga. Foque nas skills coincidentes e no valor que ele pode agregar à empresa."""

    log.info("Gerando carta para: %s @ %s (Groq/%s, %s)", title, company, GROQ_MODEL,
              "EN" if overseas else "PT-BR")

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=2000,
        temperature=0.7,
        reasoning_effort="low",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    letter = response.choices[0].message.content.strip()
    log.info("Carta gerada: %d caracteres", len(letter))
    return letter


def generate_letter_batch(jobs: list[dict]) -> dict[str, str]:
    """Gera cartas para múltiplas vagas. Retorna dict {job_id: carta}."""
    results: dict[str, str] = {}
    for job in jobs:
        job_id = job.get("id", "")
        try:
            letter = generate_cover_letter(job)
            results[job_id] = letter
        except Exception as e:
            log.error("Falha ao gerar carta para %s: %s", job_id, e)
            results[job_id] = _fallback_letter(job)
    return results


def _fallback_letter(job: dict) -> str:
    # dict.get(key, default) só retorna default se a chave não existir.
    # Se for lista vazia [], retorna [] e o join vira "". Trata os dois casos.
    skills_list = job.get("skills_match") or ["SIP", "VoIP", "BroadWorks"]

    if job.get("is_overseas"):
        title = job.get("title", "Telecommunications Analyst")
        company = job.get("company", "the company")
        skills = ", ".join(skills_list[:3])
        return f"""Dear Hiring Team at {company},

I'm interested in the {title} position and believe my experience with \
{skills} lines up directly with what you're looking for.

I've spent over 5 years working with IP telephony and VoIP, administering \
BroadWorks environments and troubleshooting SBCs in mission-critical settings, \
with direct technical dealings with carriers and SIP/CDR log analysis (Wireshark).

I'm available for a technical conversation whenever convenient for the team.

Best regards,
Erick Moreira
erickjhonatanmoreira@gmail.com"""

    title = job.get("title", "Analista de Telecomunicações")
    company = job.get("company", "empresa")
    skills = ", ".join(skills_list[:3])
    return f"""Prezados da {company},

Tenho interesse na vaga de {title} e acredito que minha experiência em {skills} \
se alinha diretamente com as necessidades descritas.

Atuo há mais de 5 anos com telefonia IP e VoIP, administrando ambientes BroadWorks \
e fazendo troubleshooting de SBCs em ambiente de missão crítica, com tratativas \
técnicas diretas junto a operadoras e análise de logs SIP/CDR (Wireshark).

Estou disponível para uma conversa técnica quando for conveniente para a equipe.

Atenciosamente,
Erick Moreira
erickjhonatanmoreira@gmail.com"""


# ─── Abordagem de recruiters (LinkedIn) ───────────────────────────────────────
# Duas peças por recrutador:
#   invite_note — vai no convite de conexão. O LinkedIn corta em 300 caracteres.
#   message     — mandada depois que ele aceita; aí cabe um pouco mais.

INVITE_LIMIT = 300

RECRUITER_SYSTEM_PROMPT = """Você escreve a abordagem de LinkedIn de Erick Moreira \
para recrutadores que publicaram vagas de Telecom/VoIP/NOC/Comunicações Unificadas.

PERFIL (use só o que está aqui, nunca invente experiência):
""" + CANDIDATE_PROFILE + """

Devolva JSON com duas chaves:
- "convite": nota do convite de conexão. NO MÁXIMO 280 caracteres. Cite a vaga
  e uma atividade concreta do perfil (não um número). Termine sem pergunta longa.
- "mensagem": mensagem para depois que o convite for aceito, até 70 palavras.
  Retome a vaga, cite 2 atividades/skills concretas do perfil que casam com
  ela (nunca um número ou resultado quantificado) e termine com uma
  pergunta simples e de baixo atrito (ex: "posso te mandar meu currículo?").

Regras: tom cordial e direto, como uma pessoa real escreveria; português
brasileiro informal-profissional; nada de "Prezado(a)" ou jargão corporativo;
nenhuma tecnologia ou resultado fora do perfil. PROIBIDO inventar números
(percentual, uptime/SLA, redução de tempo, quantidade de incidentes etc.)
— o perfil não tem métricas de resultado; cite a atividade em si, nunca um
número inventado para ela."""

RECRUITER_SYSTEM_PROMPT_EN = """You write Erick Moreira's LinkedIn outreach \
for recruiters who posted Telecom/VoIP/NOC/Unified Communications remote jobs.

PROFILE (use only what's here, never invent experience):
""" + CANDIDATE_PROFILE_EN + """

Return JSON with two keys:
- "convite": connection-request note. AT MOST 280 characters. Mention the
  job and one concrete activity from the profile (not a number). End
  without a long question.
- "mensagem": follow-up message for after the invite is accepted, up to 70
  words. Reference the job, cite 2 concrete activities/skills from the
  profile that match it (never a made-up number or quantified result), and
  end with a simple, low-friction question (e.g. "want me to send my resume?").

Rules: warm, direct tone, like a real person would write; professional but
casual English; no "Dear Sir/Madam" or corporate jargon; no technology or
result outside the profile — don't overstate spoken-English fluency, the
profile says reading/writing are advanced and speaking is still improving.
DO NOT invent numbers: no percentages, uptime/SLA metrics, time reductions,
incident counts, or any performance statistic — the profile has no result
numbers; describe the activity itself instead."""


def _fit(text: str, limit: int) -> str:
    """Corta no limite sem quebrar palavra, preferindo fim de frase."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    corte = text[:limit]
    fim = max(corte.rfind(". "), corte.rfind("! "), corte.rfind("? "))
    if fim >= limit * 0.6:
        return corte[:fim + 1].strip()
    return corte[:corte.rfind(" ")].rstrip(" ,;:") + "…"


def _best_job(recruiter: dict) -> dict:
    jobs = recruiter.get("jobs") or []
    diretas = [j for j in jobs if not j.get("inferred")] or jobs
    return max(diretas, key=lambda j: j.get("score", 0)) if diretas else {}


def generate_recruiter_outreach(recruiter: dict) -> dict:
    """Gera {'invite_note', 'message'} via Groq para um recruiter."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY não configurada")

    best = _best_job(recruiter)
    overseas = bool(best.get("is_overseas"))
    jobs = recruiter.get("jobs") or []
    first_name = (recruiter.get("name") or "").split()[0] if recruiter.get("name") else ""
    outras = len(jobs) - 1

    if overseas:
        system_prompt = RECRUITER_SYSTEM_PROMPT_EN
        user_prompt = f"""Recruiter: {recruiter.get('name', '')} (first name: {first_name})
Their title: {recruiter.get('headline', 'not informed')}

Job they posted: {best.get('title', 'a tech job')}
Company: {best.get('company', 'not informed')}
{f'They also have {outras} other relevant job(s) open.' if outras > 0 else ''}

Write the JSON with "convite" and "mensagem"."""
    else:
        system_prompt = RECRUITER_SYSTEM_PROMPT
        user_prompt = f"""Recrutador: {recruiter.get('name', '')} (primeiro nome: {first_name})
Cargo dele: {recruiter.get('headline', 'não informado')}

Vaga que ele publicou: {best.get('title', 'vaga de tecnologia')}
Empresa: {best.get('company', 'não informada')}
{f'Ele também tem outras {outras} vaga(s) da área abertas.' if outras > 0 else ''}

Escreva o JSON com "convite" e "mensagem"."""

    client = Groq(api_key=api_key)
    log.info("Gerando abordagem para recruiter: %s (Groq/%s, %s)", recruiter.get("name"), GROQ_MODEL,
              "EN" if overseas else "PT-BR")
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=1500,
        temperature=0.7,
        reasoning_effort="low",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    data = json.loads(response.choices[0].message.content)
    invite = _fit(data.get("convite", ""), INVITE_LIMIT)
    message = (data.get("mensagem") or "").strip()
    if not invite or not message:
        raise ValueError(f"resposta incompleta da Groq: {list(data)}")
    return {"invite_note": invite, "message": message}


def generate_recruiter_messages(recruiters: list[dict], limit: int = 15) -> int:
    """
    Preenche invite_note e message de quem ainda não tem, começando pelos de
    maior prioridade. `limit` protege a cota da API.
    """
    pendentes = [r for r in recruiters
                 if r.get("jobs") and not (r.get("invite_note") and r.get("message"))]
    pendentes.sort(key=lambda r: r.get("priority", 0), reverse=True)

    geradas = 0
    for rec in pendentes[:limit]:
        try:
            rec.update(generate_recruiter_outreach(rec))
            rec["outreach_source"] = "groq"
        except Exception as e:
            log.error("Falha ao gerar abordagem para %s: %s: %s",
                      rec.get("name"), type(e).__name__, e)
            rec.update(_fallback_outreach(rec))
            rec["outreach_source"] = "fallback"
        geradas += 1
    return geradas


def _fallback_outreach(recruiter: dict) -> dict:
    """Textos padrão quando a Groq falha. O convite respeita os 300 caracteres."""
    best = _best_job(recruiter)
    first_name = (recruiter.get("name") or "").split()[0] if recruiter.get("name") else ""
    empresa = best.get("company", "")

    if best.get("is_overseas"):
        hi = f"Hi {first_name}" if first_name else "Hi"
        vaga = best.get("title", "the Telecom role")
        onde = f" at {empresa}" if empresa and empresa != "N/A" else ""
        invite = _fit(
            f"{hi}! I saw your posting for {vaga}{onde}. I'm a Telecommunications "
            f"Analyst with 5 years of experience in SIP/VoIP, BroadWorks and SBC "
            f"troubleshooting in mission-critical environments. Would love to connect.",
            INVITE_LIMIT,
        )
        message = (
            f"{hi}, thanks for accepting!\n\n"
            f"About the {vaga}{onde} role: I work on administering BroadWorks "
            f"environments and troubleshooting SBCs, with direct technical dealings "
            f"with carriers.\n\n"
            f"Can I send over my resume?"
        )
        return {"invite_note": invite, "message": message}

    oi = f"Oi {first_name}" if first_name else "Oi"
    vaga = best.get("title", "a vaga de Telecom")
    onde = f" na {empresa}" if empresa and empresa != "N/A" else ""

    invite = _fit(
        f"{oi}! Vi sua vaga de {vaga}{onde}. Sou Analista de Telecomunicações há "
        f"5 anos e hoje cuido de SIP/VoIP, BroadWorks e troubleshooting de SBCs "
        f"em ambiente de missão crítica. Gostaria de me conectar.",
        INVITE_LIMIT,
    )
    message = (
        f"{oi}, obrigado por aceitar!\n\n"
        f"Sobre a vaga de {vaga}{onde}: atuo na administração de ambientes "
        f"BroadWorks e troubleshooting de SBCs, com tratativas técnicas diretas "
        f"junto a operadoras como Oi, Algar e TIP.\n\n"
        f"Posso te enviar meu currículo?"
    )
    return {"invite_note": invite, "message": message}
