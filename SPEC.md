# SPEC.md — LinkedIn ML/DS Content Pipeline

## Visão Geral

Pipeline automatizado para publicação de 3 posts semanais no LinkedIn sobre Machine Learning e Ciência de Dados. O sistema é composto por 4 agentes Python especializados, orquestrados por um script central com agendamento via `schedule` ou GitHub Actions.

---

## Estrutura de Pastas

```
linkedin-ml-pipeline/
├── SPEC.md
├── README.md
├── .env.example
├── requirements.txt
├── main.py                  # Orquestrador — ponto de entrada
├── config.py                # Configurações globais e carregamento de .env
├── agents/
│   ├── __init__.py
│   ├── researcher.py        # Agente 1: busca e seleciona tópicos
│   ├── writer.py            # Agente 2: gera texto e ilustração
│   └── scheduler.py         # Agente 3: agenda/publica no LinkedIn
├── tools/
│   ├── __init__.py
│   ├── tavily_search.py     # Wrapper da Tavily API
│   ├── arxiv_search.py      # Wrapper da arXiv API
│   ├── image_fetcher.py     # Busca imagens prontas (arXiv, HuggingFace, Unsplash, GitHub)
│   ├── code_screenshot.py   # Gera print de código via Playwright (carbon.now.sh)
│   └── linkedin_api.py      # Wrapper da LinkedIn API (OAuth 2.0)
├── prompts/
│   ├── researcher_prompt.txt
│   └── writer_prompt.txt
├── output/
│   ├── queue/               # Posts gerados aguardando publicação (JSON)
│   └── published/           # Posts já publicados (JSON, para log)
└── tests/
    ├── test_researcher.py
    ├── test_writer.py
    └── test_scheduler.py
```

---

## Variáveis de Ambiente (.env)

```env
# Anthropic
ANTHROPIC_API_KEY=

# Tavily
TAVILY_API_KEY=

# LinkedIn
LINKEDIN_CLIENT_ID=
LINKEDIN_CLIENT_SECRET=
LINKEDIN_ACCESS_TOKEN=       # Token de longa duração (60 dias, renovável)
LINKEDIN_PERSON_URN=         # urn:li:person:XXXXXXXX

# Configurações da pipeline
POSTS_PER_WEEK=3
SCHEDULE_DAYS=monday,wednesday,friday
SCHEDULE_TIME=09:00           # Horário de publicação (fuso: America/Sao_Paulo)
```

---

## Agente 1 — Researcher (`agents/researcher.py`)

### Responsabilidade
Buscar, filtrar e selecionar os tópicos mais relevantes da semana. Retorna uma lista ranqueada de candidatos a post.

### Fontes de dados

| Fonte | Ferramenta | O que buscar |
|---|---|---|
| Web geral (LinkedIn, blogs, X) | Tavily API | trending ML/DS topics last 7 days |
| Papers científicos | arXiv API (`http://export.arxiv.org/api/query`) | cs.LG, cs.AI, stat.ML — últimos 7 dias |
| Ferramentas novas | Tavily + ProductHunt RSS | new ML tools launched |

### Fluxo

```
1. Buscar 5 resultados Tavily para cada query pré-definida (ver prompts/researcher_prompt.txt)
2. Buscar 10 papers recentes no arXiv (cs.LG + cs.AI)
3. Consolidar resultados em lista única
4. Enviar lista para Claude API (claude-sonnet-4-20250514) para:
   - Deduplificar
   - Ranquear por relevância e novidade
   - Sugerir ângulo editorial para cada item
   - Classificar tipo de post: paper | tool | tutorial | trend
5. Retornar top 3 candidatos como lista de objetos ResearchResult
```

### Schema de saída (`ResearchResult`)

```python
@dataclass
class ResearchResult:
    title: str
    summary: str                  # 2-3 frases explicando o tópico
    source_url: str
    source_type: str              # "paper" | "tool" | "trend" | "tutorial"
    arxiv_id: str | None          # Ex: "2401.12345" — se for paper
    suggested_angle: str          # Ângulo editorial sugerido pelo LLM
    illustration_hint: str        # "code" | "paper_figure" | "repo_image" | "stock_photo" | "none"
    raw_sources: list[dict]       # Fontes brutas para o writer usar
```

---

## Agente 2 — Writer (`agents/writer.py`)

### Responsabilidade
Receber um `ResearchResult` e produzir o conteúdo final do post: texto formatado para LinkedIn + ilustração.

### Fluxo

```
1. Receber ResearchResult do Researcher
2. Gerar texto do post via Claude API com prompt de writer (ver prompts/writer_prompt.txt)
3. Obter ilustração de acordo com illustration_hint — prioridade em cascata:

   "paper_figure"
   └─ 1. Baixar PDF do arXiv via URL (ex: https://arxiv.org/pdf/{arxiv_id})
      2. Extrair a primeira figura/imagem relevante com PyMuPDF
      3. Se não encontrar figura útil → fallback para "repo_image"

   "repo_image"
   └─ 1. Tavily busca por "[tool name] site:github.com OR site:huggingface.co"
      2. Pegar og:image ou primeira imagem do README via requests + BeautifulSoup
      3. Se não encontrar → fallback para "stock_photo"

   "code"
   └─ 1. Claude API gera um snippet Python relevante e autocontido (max 20 linhas)
      2. Playwright abre carbon.now.sh com o código via URL encode
      3. Screenshot salvo como PNG em output/queue/images/

   "stock_photo"
   └─ 1. Buscar imagem no Unsplash (API gratuita, 50 req/hora)
         Query: tema do post em inglês (ex: "neural network", "data pipeline")
      2. Baixar tamanho "regular" (1080px) via link direto
      3. Atribuição adicionada nos metadados do PostDraft (não precisa aparecer no post)

   "none"
   └─ Publicar post apenas com texto (sem imagem)

4. Salvar PostDraft em output/queue/ como arquivo JSON
   (imagem salva em output/queue/images/{post_id}.png)
```

### Regras editoriais (embutir no writer_prompt.txt)

- **Tamanho**: 150–280 palavras (LinkedIn favorece posts médios)
- **Tom**: profissional mas acessível; evitar jargão excessivo
- **Estrutura obrigatória**:
  - 1ª linha: gancho forte (pergunta, dado surpreendente ou afirmação bold)
  - Corpo: explicação do tópico + por que importa
  - CTA final: pergunta para engajamento ("O que vocês acham?", "Já usaram?")
- **Hashtags**: 4–6 hashtags ao final (#MachineLearning, #DataScience + hashtags específicas do tópico)
- **Emojis**: usar com moderação (1–3 por post)
- **Idioma**: Português brasileiro

### Schema de saída (`PostDraft`)

```python
@dataclass
class PostDraft:
    id: str                        # UUID gerado na criação
    created_at: str                # ISO 8601
    research: ResearchResult       # Referência ao input
    text: str                      # Texto final do post
    image_path: str | None         # Caminho local da imagem (output/queue/images/)
    image_url: str | None          # URL pública de origem (paper, repo, Unsplash)
    image_credit: str | None       # Atribuição (ex: "Unsplash / @username" ou "arXiv:2401.12345")
    scheduled_for: str | None      # ISO 8601 — preenchido pelo Scheduler
    status: str                    # "draft" | "scheduled" | "published" | "failed"
```

---

## Agente 3 — Scheduler (`agents/scheduler.py`)

### Responsabilidade
Gerenciar a fila de posts e publicar no LinkedIn no horário configurado.

### Fluxo

```
1. Ler todos os JSONs em output/queue/ com status="draft"
2. Atribuir datas de publicação respeitando SCHEDULE_DAYS e SCHEDULE_TIME
3. No horário agendado:
   a. Se post tem imagem local → fazer upload via LinkedIn Asset API (registerUpload)
   b. Publicar post via POST /v2/ugcPosts com texto + asset (se houver)
   c. Mover JSON para output/published/ e atualizar status="published"
   d. Logar resultado (sucesso/falha)
```

### LinkedIn API — endpoints utilizados

```
POST https://api.linkedin.com/v2/assets?action=registerUpload   # Upload de imagem
POST https://api.linkedin.com/v2/ugcPosts                       # Publicar post
```

> ⚠️ **Atenção**: O token de acesso LinkedIn expira em 60 dias. Implementar lógica de refresh ou alerta por e-mail/log quando faltarem 10 dias para expirar.

---

## Orquestrador (`main.py`)

### Modos de execução

```bash
# Gerar 3 posts e adicionar à fila (não publica ainda)
python main.py --generate

# Publicar posts agendados para hoje
python main.py --publish

# Rodar pipeline completa: gerar + publicar
python main.py --run

# Modo contínuo com schedule interno
python main.py --daemon
```

### Fluxo principal (`--run`)

```python
def run_pipeline():
    # 1. Researcher busca e seleciona top 3 tópicos da semana
    results = researcher.fetch_weekly_topics(n=3)
    
    # 2. Writer gera post para cada tópico
    drafts = [writer.create_post(r) for r in results]
    
    # 3. Scheduler atribui datas e salva na fila
    for draft in drafts:
        scheduler.enqueue(draft)
    
    # 4. Log de resumo
    log_summary(drafts)
```

---

## Prompts

### `prompts/researcher_prompt.txt`

```
Você é um curador especializado em Machine Learning e Ciência de Dados.

Abaixo estão os resultados brutos de buscas recentes (última semana).
Sua tarefa:
1. Identifique os 3 tópicos mais relevantes, novos e interessantes para uma audiência técnica brasileira no LinkedIn.
2. Elimine duplicatas e tópicos muito nichados ou sem novidade.
3. Para cada tópico selecionado, retorne um JSON com os campos: title, summary, source_url, source_type, arxiv_id, suggested_angle, illustration_hint.
   - illustration_hint deve ser um dos valores: "paper_figure" (se for paper com figuras), "repo_image" (se for ferramenta com repositório), "code" (se o ponto central for código/API), "stock_photo" (tendência geral), "none" (último recurso).
4. Priorize: papers com resultados práticos, ferramentas novas com impacto real, tendências com dados concretos.

Retorne APENAS um array JSON válido, sem texto adicional.

RESULTADOS BRUTOS:
{raw_results}
```

### `prompts/writer_prompt.txt`

```
Você é um especialista em ML/DS e criador de conteúdo para LinkedIn.

Escreva um post em português brasileiro sobre o tópico abaixo.

REGRAS:
- Entre 150 e 280 palavras
- Comece com um gancho forte (dado surpreendente, pergunta ou afirmação)
- Explique o tópico de forma clara e acessível para um público técnico
- Termine com uma pergunta para engajar a audiência
- Inclua 4-6 hashtags relevantes ao final
- Use no máximo 3 emojis
- NÃO use bullet points excessivos — prefira parágrafos fluidos

TÓPICO:
Título: {title}
Resumo: {summary}
Ângulo sugerido: {suggested_angle}
Fonte: {source_url}

Retorne APENAS o texto do post, sem comentários adicionais.
```

---

## Dependências (`requirements.txt`)

```
anthropic>=0.25.0
tavily-python>=0.3.0
requests>=2.31.0
python-dotenv>=1.0.0
schedule>=1.2.0
playwright>=1.44.0          # Para screenshots de código (carbon.now.sh)
pymupdf>=1.24.0             # Para extrair figuras de PDFs (arXiv)
beautifulsoup4>=4.12.0      # Para extrair og:image de páginas de repositórios
Pillow>=10.0.0
dataclasses-json>=0.6.0
feedparser>=6.0.0           # Para RSS do ProductHunt
```

---

## Agendamento em Produção

### Opção A — Daemon local (`--daemon`)
Usar a lib `schedule` para rodar localmente. Simples, mas depende da máquina estar ligada.

### Opção B — GitHub Actions (recomendado)
Criar `.github/workflows/pipeline.yml` com cron:

```yaml
on:
  schedule:
    - cron: '0 12 * * 1,3,5'   # Segunda, quarta, sexta às 09:00 BRT (12:00 UTC)
```

Secrets configurados no repositório privado. Sem dependência de máquina local.

---

## Ordem de Implementação Recomendada

1. **Setup inicial**: estrutura de pastas, `.env`, `config.py`, `requirements.txt`
2. **tools/tavily_search.py** + **tools/arxiv_search.py** — validar que os dados chegam
3. **agents/researcher.py** — testar com `tests/test_researcher.py`
4. **tools/image_fetcher.py** + **tools/code_screenshot.py** — testar cada estratégia de imagem isoladamente
5. **agents/writer.py** — ajustar tom editorial iterativamente
6. **tools/linkedin_api.py** — setup OAuth, testar com post rascunho
7. **agents/scheduler.py** — testar agendamento
8. **main.py** — integrar tudo
9. **GitHub Actions** — deploy final

---

## Notas Importantes

- **LinkedIn OAuth**: Criar app em https://www.linkedin.com/developers/ — solicitar as permissões `w_member_social` e `r_liteprofile`. O fluxo de obtenção do token inicial é manual (browser); após isso, o refresh pode ser automatizado.
- **Rate limits Tavily**: plano gratuito tem 1.000 buscas/mês — suficiente para ~12 posts/mês com margem.
- **arXiv API**: sem autenticação, sem rate limit estrito — usar `time.sleep(3)` entre chamadas por boas práticas.
- **Unsplash API**: plano gratuito permite 50 requisições/hora — mais do que suficiente. Cadastro em https://unsplash.com/developers. Não é necessário exibir atribuição no post, mas salvar nos metadados é boa prática.
- **carbon.now.sh**: não tem API oficial — usar Playwright para abrir o site, preencher o código via URL params e tirar screenshot. Alternativa mais simples: usar a lib `pygments` para gerar um HTML com syntax highlighting e converter para imagem com Playwright.
- **Custo total estimado**: R$ 0/mês (todas as ferramentas usadas têm plano gratuito suficiente para a escala do projeto).