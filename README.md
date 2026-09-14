# 📡 Job Radar — Erick Moreira

Sistema automatizado de busca e candidatura em vagas de Telecom/VoIP/NOC.
Roda 100% gratuito via GitHub Actions + GitHub Pages.

> Fork de [EricDiasLemos/radar](https://github.com/EricDiasLemos/radar), adaptado
> para o perfil de Analista de Telecomunicações (SIP/VoIP/BroadWorks/SBC/NOC).

## Estrutura

```
job-radar/
├── .github/workflows/
│   ├── daily-scan.yml        # Roda seg–sex às 08h BRT
│   └── manual-apply.yml      # Candidatura avulsa pelo dashboard
├── scripts/
│   ├── main.py               # Orquestrador (entry point)
│   ├── scraper.py            # Busca vagas (LinkedIn/Vagas.com/Remotive)
│   ├── scorer.py             # Calcula fit score 0–100
│   ├── letter_gen.py         # Gera carta via Groq (gratuito)
│   └── mailer.py             # Envia email com currículo
├── data/
│   ├── jobs.json             # Banco de vagas
│   └── sent.json             # Histórico de candidaturas
├── docs/
│   └── index.html            # Interface (GitHub Pages)
├── assets/
│   └── curriculo.pdf         # ← Adicione seu currículo aqui
└── requirements.txt
```

## Setup — passo a passo

### 1. Fork / clone o repositório

```bash
git clone https://github.com/ErickMain/radar.git
cd radar
```

### 2. Adicione o currículo

Coloque o arquivo PDF em `assets/curriculo.pdf`.

### 3. Configure os GitHub Secrets

Vá em **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Valor |
|--------|-------|
| `GROQ_API_KEY` | Chave da API Groq, gratuita (console.groq.com) |
| `GMAIL_USER` | Seu email Gmail (ex: erickjhonatanmoreira@gmail.com) |
| `GMAIL_APP_PASSWORD` | Senha de app do Gmail (não a senha normal) |
| `CANDIDATE_EMAIL` | Email para receber as candidaturas |

> **Como criar Gmail App Password:**
> Google Account → Segurança → Verificação em duas etapas → Senhas de app

### 4. Configure o GitHub Pages

- Settings → Pages → Source: **GitHub Actions**
- Ou: Source → Deploy from branch → `gh-pages` / `/ (root)`

### 5. Edite o dashboard

Em `docs/index.html`, as constantes no topo do `<script>` já apontam para este fork:

```js
const GITHUB_OWNER = 'ErickMain';
const GITHUB_REPO  = 'radar';
```

### 6. Configure o token no dashboard

Para usar os botões "Forçar scan" e "Candidatar" no dashboard, abra o console do browser (F12) e rode:

```js
localStorage.setItem("gh_token", "ghp_SEU_PERSONAL_ACCESS_TOKEN")
```

Crie o token em: **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained**
Permissões necessárias: `Actions: write`

### 7. Faça o primeiro commit e push

```bash
git add .
git commit -m "feat: initial job radar setup"
git push
```

O workflow roda automaticamente na próxima seg–sex às 08h BRT,
ou acesse **Actions → Job Radar — Daily Scan → Run workflow** para rodar agora.

---

## Como funciona o scoring

| Critério | Peso |
|----------|------|
| Skills match | até 40 pts |
| Localização (BH/Remoto/Híbrido) | 20 pts |
| Nível (júnior/pleno) | 20 pts |
| Keywords positivas (inclui inglês) | até 10 pts |
| Salário | até 10 pts |
| 🌍 Remoto internacional | até 15 pts |
| 🎯 Empresa alvo | até 20 pts |
| 🌱 Skills de crescimento | até 10 pts |

- **Score ≥ 70** (ou ≥ 60 para empresa alvo / remoto internacional) → 🟢 Alto fit — candidatura automática
- **Score 50–69** → 🟡 Médio fit — aprovação manual no dashboard
- **Score < 50** → 🔴 Baixo fit — arquivado

Vagas com keywords negativas (Sênior 8+, Arquiteto, CTO, Mobile...) são rejeitadas automaticamente.
Cargos fora de Telecom/VoIP/NOC (ex: DevOps, Cloud puro) são classificados como
"adjacent" — área de crescimento, mas não pontuados nem candidatados automaticamente.

### Foco em remoto internacional

O candidato prioriza vagas remotas, inclusive fora do Brasil — inglês avançado
para leitura/escrita, fala ainda em desenvolvimento (por isso o foco é suporte
remoto assíncrono: email/chat/ticket, não atendimento telefônico constante).

- Vagas achadas via **LinkedIn Worldwide** (sem travar em ", Brasil", filtro
  `f_WT=2` = só remoto) ou via **Remotive** (API de vagas 100% remotas
  internacionais) são marcadas `is_overseas: true`.
- Essas vagas recebem localização máxima (remoto por definição), o bonus de
  +15 "🌍 Remoto internacional", e o threshold de alto fit cai para 60 (igual
  ao de empresa alvo).
- **Carta de apresentação e abordagem de recrutador são geradas em inglês**
  para essas vagas (`letter_gen.py` decide o idioma pelo campo `is_overseas`),
  sempre com base só no perfil real — nunca inventa fluência que o candidato
  não tem.
- ⚠️ Limitação conhecida: o currículo anexado (`assets/curriculo.pdf`) está em
  português mesmo para vagas overseas — ainda não há uma versão em inglês.

---

## Execução local

```bash
pip install -r requirements.txt

# Apenas scraping + scoring (sem envio de emails)
PYTHONPATH=scripts python scripts/main.py scan --no-auto-apply

# Candidatura manual para uma vaga específica
GROQ_API_KEY=... GMAIL_USER=... GMAIL_APP_PASSWORD=... \
PYTHONPATH=scripts python scripts/main.py apply <job_id>
```

---

## Fontes de vagas

- **LinkedIn Jobs** — API pública guest (sem login); busca no Brasil (BH/MG)
  e Worldwide/remoto (sem restrição de país). De longe a fonte principal —
  full-text search melhor que a busca por categoria do Vagas.com
- **Vagas.com** — vagas.com.br (Brasil). Inventário fraco pro nicho de
  telecom/VoIP: a busca deles é frouxa, a maioria das queries retorna ruído
  (analista de atendimento, administrativo etc.) que o portão de cargo do
  scorer descarta — por isso "0 vagas encontradas" é o resultado normal na
  maior parte das buscas, não um bug
- **Programathor** — RSS feed (Brasil)
- **Remotive** — remotive.com API, vagas 100% remotas internacionais
- ~~**Gupy**~~ — desativado em 2026-09: portal.api.gupy.io descontinuado
  (404 até na raiz do domínio). `scrape_gupy()` ficou no código caso um
  endpoint novo apareça, mas não é mais chamada em `run_scraper()`

Rate limiting e user-agents rotativos estão configurados para evitar bloqueio.
Cada fonte tem fallback gracioso — se uma estiver indisponível, as demais continuam.
