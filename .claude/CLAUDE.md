# CLAUDE.md — Instruções do Projeto

> Leia este arquivo no início de cada sessão. Ele define como eu trabalho, o que eu priorizo e como você deve me ajudar.

---

## 👤 Perfil e contexto

Sou **cientista de dados e engenheiro de ML** que também desenvolve software de propósito geral. Meus projetos variam entre:

- Pipelines de dados e ETL (Pandas, PySpark, DuckDB)
- Modelos de ML/DL e experimentos (scikit-learn, PyTorch, XGBoost)
- Sistemas RAG e aplicações com LLMs
- APIs e serviços backend (FastAPI, Flask)
- Scripts de automação e ferramentas internas
- Análises exploratórias em notebooks (Jupyter, VS Code)

**Stack principal:** Python · SQL · FastAPI · Docker · Git · MLflow/W&B · LangChain/LlamaIndex

---

## 🧠 Filosofia geral

**Clareza antes de elegância.** Código que qualquer engenheiro entende em 30 segundos vale mais do que código "inteligente" que ninguém quer manter.

**Modularidade sem overengineering.** Abstraia o que for repetido. Não abstraia o que for incerto. Se você não tem dois casos de uso concretos para uma abstração, não a crie ainda.

**Faça a coisa funcionar, depois melhore.** Evite otimizações prematuras — especialmente em ML, onde o gargalo raramente é onde você imagina.

---

## 🏗️ Arquitetura de software

### Princípios

- **Separação de responsabilidades:** cada módulo tem uma razão clara para existir e uma razão clara para mudar.
- **Dependências explícitas:** prefira injeção de dependências a estado global. Evite imports com side effects.
- **Fail fast, fail loud:** valide entradas cedo. Prefira exceções informativas a estados silenciosamente inválidos.
- **Sem magia implícita:** evite metaprogramação pesada, decoradores complexos encadeados e herança profunda sem necessidade real.

### Estrutura de projeto padrão

```
project/
├── src/
│   └── project_name/
│       ├── __init__.py
│       ├── config.py          # Configurações e constantes
│       ├── models/            # Modelos de domínio / schemas (Pydantic)
│       ├── services/          # Lógica de negócio
│       ├── repositories/      # Acesso a dados (DB, arquivos, APIs)
│       └── utils/             # Funções auxiliares puras
├── tests/
│   ├── unit/
│   └── integration/
├── notebooks/                 # Exploração e análise (não produção)
├── scripts/                   # Utilitários de linha de comando
├── data/
│   ├── raw/                   # Dados originais — nunca modificar
│   ├── processed/             # Dados transformados
│   └── external/              # Dados de fontes externas
├── pyproject.toml
├── .env.example
└── README.md
```

### Regras de modularidade

- **Funções:** máximo ~30 linhas. Se estiver passando disso, provavelmente faz mais de uma coisa.
- **Classes:** prefira composição a herança. Use herança apenas quando a relação "é um" é genuinamente verdadeira.
- **Módulos:** um módulo = um conceito. Se o nome do módulo precisar de "e" (ex: `utils_and_helpers.py`), separe-o.
- **Não extraia prematuramente:** um helper que é usado em um único lugar pode ficar inline até existir um segundo uso real.

### APIs e serviços

```python
# Prefira schemas Pydantic explícitos em todas as fronteiras
class PredictionRequest(BaseModel):
    features: dict[str, float]
    model_version: str = "latest"

class PredictionResponse(BaseModel):
    prediction: float
    confidence: float
    model_version: str
    latency_ms: float
```

- Versione APIs desde o início (`/v1/`, `/v2/`).
- Documente com OpenAPI — FastAPI gera automaticamente, use-o.
- Retorne erros estruturados, nunca strings brutas.

---

## 🤖 Metodologia de ML

### Estrutura de projeto ML

```
ml_project/
├── src/
│   └── ml_project/
│       ├── data/
│       │   ├── ingestion.py      # Carregamento de dados brutos
│       │   ├── validation.py     # Checks de qualidade e schema
│       │   └── preprocessing.py  # Transformações reproduzíveis
│       ├── features/
│       │   ├── engineering.py    # Criação de features
│       │   └── selection.py      # Seleção e filtragem
│       ├── models/
│       │   ├── base.py           # Interface comum dos modelos
│       │   ├── train.py          # Loop de treino
│       │   └── evaluate.py       # Métricas e avaliação
│       └── pipelines/
│           ├── training.py       # Pipeline de treino end-to-end
│           └── inference.py      # Pipeline de inferência
├── notebooks/
│   ├── 01_eda.ipynb
│   ├── 02_feature_engineering.ipynb
│   └── 03_model_selection.ipynb
├── experiments/                  # Configs de experimentos (YAML)
├── models/                       # Artefatos serializados
└── mlflow/ ou wandb/             # Tracking local (se aplicável)
```

### Princípios de experimentação

- **Toda rodada de treino é rastreada.** Nenhum experimento sem logging de hiperparâmetros, métricas e artefatos (MLflow ou W&B).
- **Reprodutibilidade não é opcional.** Seeds fixos, versão dos dados, versão do código. Se não consegue reproduzir, o experimento não aconteceu.
- **Baseline primeiro.** Sempre comece com um modelo simples (regressão logística, média histórica, regra de negócio). O modelo complexo precisa superar o baseline de forma justificável.
- **Separe treino de inferência.** O código de inferência em produção não deve depender de nada do loop de treino.

### Pipelines reproduzíveis

```python
# Use sklearn Pipeline ou equivalente — nunca transformações avulsas
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

pipeline = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("scaler", StandardScaler()),
    ("model", XGBClassifier(**params)),
])

# Serialize sempre o pipeline completo, não apenas o modelo
joblib.dump(pipeline, "models/pipeline_v1.pkl")
```

### Validação e avaliação

- **Nunca avalie no treino.** Sempre holdout ou cross-validation.
- **Escolha métricas com propósito.** Accuracy raramente é a métrica certa. Defina a métrica de negócio antes de treinar.
- **Documente data leakage checks** explicitamente nos notebooks de EDA.
- **Feature importance é diagnóstico, não explicação causal.** Não confunda correlação com causalidade nos relatórios.

### RAG e LLMs

```python
# Estruture retrieval e geração como estágios separados e testáveis
class RAGPipeline:
    def __init__(self, retriever: BaseRetriever, llm: BaseLLM):
        self.retriever = retriever  # testável de forma isolada
        self.llm = llm

    def query(self, question: str, top_k: int = 5) -> RAGResponse:
        docs = self.retriever.retrieve(question, top_k=top_k)
        context = self._format_context(docs)
        answer = self.llm.generate(question, context)
        return RAGResponse(answer=answer, sources=docs)
```

- Avalie retrieval separado de geração (recall@k, MRR para retrieval; fidelidade, relevância para geração).
- Versione seus índices de embedding junto com o modelo de embedding usado.
- Documente chunking strategy e racional (tamanho, overlap, método).

---

## ✍️ Clean code

### Nomes

- **Variáveis e funções:** verbos para funções (`load_features`, `compute_rmse`), substantivos para dados (`user_features`, `raw_predictions`).
- **Evite abreviações** a não ser que sejam convenção estabelecida da área (`df` para DataFrame, `lr` para learning rate são aceitáveis).
- **Booleanos começam com `is_`, `has_`, `should_`** (`is_trained`, `has_nulls`, `should_retrain`).

```python
# Ruim
def proc(d, fl=True):
    r = d[d['v'] > 0]
    return r if fl else r.head()

# Bom
def filter_positive_values(data: pd.DataFrame, return_all: bool = True) -> pd.DataFrame:
    positive_rows = data[data['value'] > 0]
    return positive_rows if return_all else positive_rows.head()
```

### Type hints — sempre

```python
from typing import Optional
import pandas as pd

def compute_metrics(
    y_true: pd.Series,
    y_pred: pd.Series,
    threshold: float = 0.5,
) -> dict[str, float]:
    ...
```

### Docstrings — quando agrega valor

Use docstrings em funções públicas de módulos reutilizáveis. Não documente o óbvio.

```python
def split_time_series(
    df: pd.DataFrame,
    date_col: str,
    cutoff_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Divide um DataFrame temporal respeitando a ordem cronológica.

    Não usa shuffle — garante que dados futuros não vazem para o treino.

    Returns:
        (train_df, test_df) onde train_df contém registros anteriores ao cutoff.
    """
```

### Tratamento de erros

```python
# Exceções específicas com contexto
class DataValidationError(Exception):
    """Levantada quando o schema dos dados de entrada não corresponde ao esperado."""

def validate_features(df: pd.DataFrame, required_cols: list[str]) -> None:
    missing = set(required_cols) - set(df.columns)
    if missing:
        raise DataValidationError(
            f"Colunas obrigatórias ausentes: {missing}. "
            f"Colunas disponíveis: {list(df.columns)}"
        )
```

- Nunca use `except Exception` sem re-raise ou logging explícito.
- Nunca silencie erros com `pass`.

### Configuração

```python
# Use Pydantic Settings — nunca hardcode nem misture config com lógica
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    model_path: str = "models/pipeline_v1.pkl"
    log_level: str = "INFO"
    mlflow_tracking_uri: str = "http://localhost:5000"

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 📓 Notebooks — análise e exploração

### Filosofia

Notebooks são **ferramentas de análise e comunicação**, não de produção. Código de notebook que precisa ser reutilizado deve ser refatorado para um módulo Python.

### Convenções

- **Nomeação:** `NN_descricao_curta.ipynb` (ex: `01_eda_churn.ipynb`, `03_feature_selection.ipynb`)
- **Estrutura padrão de um notebook:**

```
# 0. Setup e imports
# 1. Carregamento de dados
# 2. Inspeção inicial (shape, dtypes, missing values)
# 3. Análise / experimento principal
# 4. Conclusões e próximos passos
```

- A célula de setup carrega variáveis de ambiente e registra a versão dos dados usados.
- **Outputs comitados no Git** somente para notebooks de relatório final. Notebooks de exploração: limpe os outputs antes de commitar (`nbstripout`).

### Análise externa com notebooks

Quando for analisar dados ou resultados de um sistema externo:

```python
# Sempre documente a origem dos dados na célula de carregamento
# Fonte: API interna /v1/events — snapshot de 2024-03-15
# Versão do schema: v2.3

df = pd.read_parquet("data/raw/events_2024-03-15.parquet")
print(f"Shape: {df.shape}")
print(f"Período: {df['timestamp'].min()} → {df['timestamp'].max()}")
print(f"Missing values:\n{df.isnull().sum()[df.isnull().sum() > 0]}")
```

- Documente **hipóteses** antes de plotar. Escreva o que você espera ver antes de ver.
- Documente **conclusões negativas** — "não encontrei correlação entre X e Y" é tão valioso quanto encontrar.
- Use `assert` para invariantes que você assumiu sobre os dados.

### Boas práticas de visualização

```python
import matplotlib.pyplot as plt
import seaborn as sns

# Configuração padrão — aplique no início do notebook
sns.set_theme(style="whitegrid", palette="muted")
plt.rcParams.update({"figure.dpi": 120, "figure.figsize": (10, 5)})

# Toda figura tem título, labels e fonte dos dados
fig, ax = plt.subplots()
ax.set_title("Distribuição de churn por faixa de tenure", fontsize=13)
ax.set_xlabel("Tenure (meses)")
ax.set_ylabel("Taxa de churn")
fig.text(0.99, 0.01, "Fonte: CRM snapshot 2024-Q1", ha="right", fontsize=8, color="gray")
```

---

## 🧪 Testes

### O que testar obrigatoriamente

- Funções de transformação de dados (entradas e saídas com casos extremos)
- Validação de schemas (colunas ausentes, tipos errados, nulls inesperados)
- Lógica de negócio em `services/`
- Endpoints de API (status codes, formato de resposta)

### O que não precisa de teste unitário

- Notebooks de exploração
- Scripts one-shot de migração
- Wrappers triviais sem lógica própria

### Estrutura

```python
# tests/unit/test_preprocessing.py
import pytest
import pandas as pd
from project.data.preprocessing import filter_positive_values

def test_filter_positive_values_removes_negatives():
    df = pd.DataFrame({"value": [-1, 0, 1, 2]})
    result = filter_positive_values(df)
    assert all(result["value"] > 0)

def test_filter_positive_values_raises_on_missing_column():
    df = pd.DataFrame({"other_col": [1, 2]})
    with pytest.raises(KeyError):
        filter_positive_values(df)
```

- Use `pytest` como padrão.
- Fixtures de dados em `conftest.py`.
- Prefira testes pequenos e focados. Um `assert` por teste sempre que possível.

---

## 🔁 Git e versionamento

### Commits

Siga **Conventional Commits**:

```
feat: adiciona endpoint de predição batch
fix: corrige data leakage no split temporal
refactor: extrai lógica de validação para módulo próprio
data: atualiza snapshot de features para 2024-Q2
experiment: testa XGBoost com feature selection por SHAP
docs: documenta pipeline de inferência
```

- Commits atômicos: uma mudança lógica por commit.
- Nunca commite `.env`, credenciais, dados brutos grandes ou artefatos de modelo diretamente (use DVC ou storage externo).

### `.gitignore` padrão

```
.env
*.pkl
*.joblib
*.h5
*.pt
data/raw/
data/processed/
mlruns/
wandb/
__pycache__/
.ipynb_checkpoints/
```

---

## 📦 Dependências e ambiente

- Use `pyproject.toml` com `uv` ou `poetry` para gerenciamento.
- Separe dependências de dev das de produção.
- Pin versões em produção. Use ranges em bibliotecas.
- Documente no `README.md` como criar o ambiente do zero em menos de 3 comandos.

---

## 🚀 Como me ajudar (instruções para o Claude)

### Ao escrever código novo

1. Siga as convenções de nomenclatura e estrutura definidas acima.
2. Inclua type hints em todas as funções.
3. Prefira soluções simples. Se houver uma abordagem com menos abstrações que resolve o problema, use-a.
4. Sugira testes quando criar funções de lógica de negócio ou transformação.
5. Avise quando estiver criando uma abstração que pode ser prematura.

### Ao revisar código existente

1. Priorize problemas reais (bugs, data leakage, ausência de validação) antes de style.
2. Explique o *porquê* das sugestões, não só o *o quê*.
3. Não refatore por refatorar — só sugira se há ganho concreto de legibilidade ou manutenibilidade.

### Ao trabalhar em notebooks

1. Mantenha a estrutura de seções definida acima.
2. Documente hipóteses e conclusões, não apenas código.
3. Sinalize quando um trecho de notebook deve ser movido para um módulo Python.

### Ao trabalhar em ML

1. Sempre questione se a métrica escolhida é a certa para o problema de negócio.
2. Sugira baseline simples antes de modelos complexos.
3. Alerte sobre potencial data leakage em qualquer transformação que use estatísticas do dataset inteiro.
4. Lembre de registrar o experimento no tracker (MLflow/W&B) quando criar loops de treino.

### Ao projetar APIs e serviços

1. Sugira schemas Pydantic para todas as fronteiras de entrada/saída.
2. Separe a lógica de rota (controller) da lógica de negócio (service).
3. Lembre de versionar endpoints desde o início.

### Formato das respostas

- **Código primeiro** quando a tarefa é clara. Explique depois se necessário.
- **Pergunte antes de assumir** quando a tarefa for ambígua — especialmente sobre contexto de dados e constraints de produção.
- **Seja direto.** Não adicione disclaimers genéricos ou aviso de "lembre-se sempre de testar em produção" a menos que seja genuinamente relevante para o caso.
- **Proponha alternativas** quando houver trade-off real entre abordagens, com prós e contras concretos.
