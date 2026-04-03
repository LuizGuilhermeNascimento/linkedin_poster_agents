## Visão Geral

Pipeline automatizado para geração de 3 posts semanais sobre Machine Learning e Ciência de Dados. O sistema é composto por 2 agentes Python especializados orquestrados por um script central. Posts gerados são salvos localmente em pastas organizadas — a publicação no LinkedIn fica a cargo do usuário.

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
│   └── writer.py            # Agente 2: gera texto e ilustração
├── tools/
│   ├── __init__.py
│   ├── tavily_search.py     # Wrapper da Tavily API
│   ├── arxiv_search.py      # Wrapper da arXiv API
│   ├── image_fetcher.py     # Busca imagens prontas (arXiv, HuggingFace, Unsplash, GitHub)
│   └── code_screenshot.py   # Gera print de código via Playwright (carbon.now.sh)
├── prompts/
│   ├── researcher_prompt.txt
│   └── writer_prompt.txt
└── output/
    ├── YYYY-WW/             # Uma pasta por semana (ex: 2025-28/)
    │   ├── post_1/
    │   │   ├── post.txt     # Texto final do post
    │   │   ├── image.png    # Imagem (se houver)
    │   │   └── meta.json    # Metadados completos (ResearchResult + PostDraft)
    │   ├── post_2/
    │   └── post_3/
    └── ...
```

---

## Variáveis de Ambiente (.env)

```env
# Anthropic
ANTHROPIC_API_KEY=

# Tavily
TAVILY_API_KEY=

# Unsplash (opcional — só necessário se illustration_hint="stock_photo")
UNSPLASH_ACCESS_KEY=

# Configurações da pipeline
POSTS_PER_WEEK=3
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
   - Deduplicar
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
Receber um `ResearchResult` e produzir o conteúdo final do post: texto formatado para LinkedIn + ilustração. Salvar tudo localmente.

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
      3. Screenshot salvo como image.png

   "stock_photo"
   └─ 1. Buscar imagem no Unsplash (API gratuita, 50 req/hora)
      2. Baixar tamanho "regular" (1080px) via link direto
      3. Atribuição registrada em meta.json

   "none"
   └─ Salvar post apenas com texto (sem image.png)

4. Criar pasta de destino: output/YYYY-WW/post_N/
5. Salvar os 3 arquivos:
   - post.txt  → texto final pronto para copiar e colar no LinkedIn
   - image.png → ilustração (se houver)
   - meta.json → metadados completos (ver PostDraft abaixo)
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

### Schema de saída (`PostDraft`) — salvo em `meta.json`

```python
@dataclass
class PostDraft:
    id: str                        # UUID gerado na criação
    created_at: str                # ISO 8601
    week: str                      # Ex: "2025-28" (ano-semana ISO)
    research: ResearchResult       # Referência ao input
    text: str                      # Texto final do post
    image_path: str | None         # Caminho relativo: "output/2025-28/post_1/image.png"
    image_url: str | None          # URL pública de origem (paper, repo, Unsplash)
    image_credit: str | None       # Atribuição (ex: "Unsplash / @username" ou "arXiv:2401.12345")
    status: str                    # "draft" (único valor — publicação é manual)
```

---

## Orquestrador (`main.py`)

### Modos de execução

```bash
# Gerar 3 posts da semana e salvar em output/YYYY-WW/
python main.py --generate

# Forçar regeneração mesmo que a pasta da semana já exista
python main.py --generate --force
```

### Fluxo principal (`--generate`)

```python
def run_pipeline():
    week_label = get_current_week()          # Ex: "2025-28"
    output_dir = Path(f"output/{week_label}")

    # 1. Researcher busca e seleciona top 3 tópicos da semana
    results = researcher.fetch_weekly_topics(n=3)

    # 2. Writer gera post + imagem para cada tópico e salva localmente
    for i, result in enumerate(results, start=1):
        post_dir = output_dir / f"post_{i}"
        writer.create_post(result, output_dir=post_dir)

    # 3. Log de resumo
    log_summary(output_dir)
```

### Saída esperada no terminal

```
[2025-W28] Gerando 3 posts...
  post_1 → "Mamba 2: arquitetura SSM supera Transformers em contextos longos" ✓
  post_2 → "LangGraph v0.2: novo paradigma para agentes com estado" ✓
  post_3 → "Meta lança dataset SA-1B com 1 bilhão de máscaras" ✓

Salvo em: output/2025-28/
  post_1/  post.txt  image.png  meta.json
  post_2/  post.txt  image.png  meta.json
  post_3/  post.txt  (sem imagem)  meta.json
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
3. Para cada tópico selecionado, retorne um JSON com os campos: title, summary, source_url,
   source_type, arxiv_id, suggested_angle, illustration_hint.
   - illustration_hint deve ser: "paper_figure" | "repo_image" | "code" | "stock_photo" | "none"
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
playwright>=1.44.0          # Para screenshots de código (carbon.now.sh)
pymupdf>=1.24.0             # Para extrair figuras de PDFs (arXiv)
beautifulsoup4>=4.12.0      # Para extrair og:image de páginas de repositórios
Pillow>=10.0.0
dataclasses-json>=0.6.0
feedparser>=6.0.0           # Para RSS do ProductHunt
```

> `schedule` removido — sem daemon, sem agendamento interno.

---

## Notas Importantes

- **Saída local apenas**: nenhuma credencial do LinkedIn é necessária. Os arquivos `post.txt` ficam prontos para copiar e colar diretamente na interface do LinkedIn.
- **Organização por semana ISO**: a pasta `output/YYYY-WW/` garante histórico organizado sem risco de sobrescrever posts anteriores.
- **Rate limits Tavily**: plano gratuito tem 1.000 buscas/mês — suficiente para ~12 rodadas/mês com margem.
- **arXiv API**: sem autenticação — usar `time.sleep(3)` entre chamadas por boas práticas.
- **Unsplash API**: plano gratuito permite 50 requisições/hora. Cadastro em https://unsplash.com/developers. Atribuição salva em `meta.json`.
- **carbon.now.sh**: sem API oficial — usar Playwright com URL params. Alternativa: `pygments` para syntax highlighting em HTML, convertido para PNG via Playwright.
- **Custo total estimado**: R$ 0/mês (todas as ferramentas usadas têm plano gratuito suficiente para a escala do projeto).