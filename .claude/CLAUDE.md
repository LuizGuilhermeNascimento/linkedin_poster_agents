# CLAUDE.md — Design and Architecture Guidelines for Claude

> Read this file at the start of each session. It defines the architecture, conventions, and patterns.

---

## Directory Structure

```
src/
├── api/                    # (optional) HTTP interface — only present when the project exposes an API
│   ├── dependencies.py     # DI factories; constructs and caches service instances
│   └── routes/             # One file per resource/domain; thin controllers, no business logic
├── core/                   # Cross-cutting infrastructure shared by the whole application
│   ├── config.py           # All configuration — Pydantic Settings reading from env vars
│   ├── exceptions.py       # Custom exception types with structured context
│   ├── health_check.py     # Liveness/readiness probes (verifies real dependencies)
│   └── telemetry.py        # Tracing/metrics setup + trace_function decorator
├── models/                 # Data contracts: request/response schemas and domain types
│   └── schemas.py          # All Pydantic models in one place (split by domain if large)
├── services/               # Business logic; one service per bounded context
│   └── <domain>_service.py # Orchestrates utils, repositories, and external clients
├── utils/                  # Pure, stateless functions — no I/O, no side effects
│   └── <concern>.py        # Group by concern (e.g. parsing, validation, calculation)
├── config/                 # Non-code configuration (JSON/YAML rule files, lookup tables)
│   └── *.json              # Thresholds, mappings, rule sets — loaded at startup
└── main.py                 # Entry point: app factory, lifespan hooks, top-level wiring
tests/
├── test_<module>.py        # Mirror src/ structure — one test file per source module
├── pytest.ini              # pytest config: asyncio mode, coverage, markers
└── requirements.txt        # Test-only dependencies
```

### Directory rules

| Directory | Contains | Does NOT contain |
|-----------|----------|-----------------|
| `api/` | Route definitions, DI wiring | Business logic, direct DB/cache calls |
| `core/` | Infra primitives reused everywhere | Domain logic, service orchestration |
| `models/` | Pydantic types (input, output, domain) | Transformation logic, I/O |
| `services/` | Orchestration — calls utils + external clients | HTTP handling, config reads |
| `utils/` | Pure functions with typed in/out | State, I/O, class instances |
| `config/` | Data files driving configurable behaviour | Python logic |
| `tests/` | Test code only | Application code |

`src/api/` is **optional** — omit it entirely for scripts, pipelines, or worker processes. The rest of the structure applies regardless of project type.

---

## Architecture

### Layered Architecture

```
Entry Point     (src/main.py)             — App factory, startup, top-level wiring
Interface Layer (src/api/routes/)         — Thin controllers; translate I/O to domain calls
                                            (omit for non-API projects; use CLI / worker instead)
Service Layer   (src/services/)           — Business logic orchestration
Utility Layer   (src/utils/)              — Pure functions; no I/O, no dependencies
Data Layer      (services that own I/O)   — External systems: DBs, caches, APIs, queues
Core            (src/core/)               — Infra primitives: config, exceptions, telemetry
Models          (src/models/schemas.py)   — Typed contracts between all layers
```

Each layer only depends on layers below it. Services may call utils and data-layer clients; they never import from `api/`.

### Dependency Injection

All services are constructed via factory functions in `src/api/dependencies.py` using `@lru_cache()` for singleton behavior. Routes receive services via FastAPI's `Depends()`.

```python
@lru_cache()
def get_report_service() -> ReportService:
    return ReportService(llm=get_llm_manager(), business_rules=get_business_rules())

# In route:
@router.post("/report")
async def generate_report(
    request: ReportRequest,
    report_service: ReportService = Depends(get_report_service),
):
```

Never instantiate services directly inside route handlers or other services.


## Key Conventions

### Configuration

All config is via environment variables mapped to Pydantic `BaseSettings` subclasses in `src/core/config.py`. Each concern has its own settings class:

```python
class RedisSettings(BaseSettings):
    host: str = Field("localhost", alias="REDIS_HOST")
    port: int = Field(6379, alias="REDIS_PORT")

    model_config = SettingsConfigDict(populate_by_name=True)

class Settings(BaseSettings):
    redis: RedisSettings = RedisSettings()
    # ... other settings

settings = Settings()  # singleton — import and use directly
```

Never hardcode values. Never put config logic in service files.

### Schemas

All API boundaries use Pydantic models from `src/models/schemas.py`. No raw dicts at service interfaces.

```python
class ReportRequest(BaseModel):
    store_id: str
    product_id: str
    diagnosis: DiagnosisType  # Literal enum
    reference_month: str      # validated format YYYY-MM
    company_id: str

class ReportResponse(BaseModel):
    diagnosis: str
    report: list[ReportItem]
    report_type: Literal["verifiable", "unverifiable"]
```

### Services

Services are classes with injected dependencies. Methods are async when they touch I/O:

```python
class MetricService:
    def __init__(self, cube_client: CubeClient, cache_service: CacheService):
        self._cube = cube_client
        self._cache = cache_service
        self._logger = build_logger(__name__)

    async def get_product_data(self, request: ReportRequest) -> ProductData:
        ...
```

- Validate inputs early, raise custom exceptions from `src/core/exceptions.py`


### Exception Handling

Use custom exceptions from `src/core/exceptions.py`. Catch broad exceptions at service boundaries, log context, re-raise as domain exceptions:

```python
try:
    response = await self._cube.query(...)
except Exception as e:
    self._logger.error("CubeJS query failed", error=str(e))
    raise ExternalServiceError("Failed to fetch product data") from e
```

Never use bare `except: pass`. Never return error strings from services.