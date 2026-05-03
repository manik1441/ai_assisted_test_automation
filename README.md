# 🤖 Agentic TestGen Framework (ATF)

> An **AI-driven test automation platform** that generates, reviews, and executes
> UI, API, and DB test scripts from natural language prompts — powered by OpenRouter LLMs,
> Playwright, Pytest, and ChromaDB.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [CLI Usage](#cli-usage)
- [Agent Reference](#agent-reference)
- [Jira Integration](#jira-integration)
- [CI/CD](#cicd)
- [Roadmap](#roadmap)

---

## Overview

ATF turns a plain English test requirement into a runnable pytest test suite — automatically.

**What it does:**

1. Accepts a **natural language prompt**, a **Jira ticket**, or both
2. Classifies the test type (`ui` / `api` / `db`) via the **Lead Agent**
3. Decomposes the intent into discrete tasks via the **Task Planner**
4. Generates test scenarios via specialist agents (**UI / API / DB**)
5. Converts scenarios into **executable pytest scripts** (Playwright, requests, SQLAlchemy)
6. **Reviews** every script for best-practice compliance
7. **Executes** the tests and produces an **Allure report**
8. Optionally **writes results back to Jira** and generates **CI/CD pipeline YAML**

---

## Architecture

```
User Prompt / Jira Ticket
         │
         ▼
   ┌─────────────┐
   │ Orchestrator │  ← single entry point, dependency injection
   └──────┬──────┘
          │
   ┌──────▼──────┐
   │  Lead Agent  │  ← intent detection + test type classification
   └──────┬──────┘
          │
   ┌──────▼──────┐
   │ Task Planner │  ← decomposes intent into ordered task list
   └──────┬──────┘
          │
   ┌──────▼──────────────┐
   │ UI / API / DB Agent  │  ← specialist scenario generation
   └──────┬──────────────┘
          │
   ┌──────▼──────────┐
   │ Test Script Agent│  ← generates pytest-compatible scripts
   └──────┬──────────┘
          │
   ┌──────▼──────┐
   │ Review Agent │  ← syntax, best-practice, flakiness checks
   └──────┬──────┘
          │
   ┌──────▼──────────┐
   │ Execution Engine │  ← pytest + Playwright runner
   └──────┬──────────┘
          │
   ┌──────▼──────┐
   │ Report Agent │  ← Allure results + JSON summary
   └──────┬──────┘
          │
   ┌──────▼──────┐
   │  CI/CD Agent │  ← GitHub Actions / GitLab CI YAML
   └─────────────┘
```

**Cross-cutting concerns:**
- **MessageBus** — in-process typed event log for inter-agent communication
- **ChromaDB** — vector memory for prompts, scripts, and locator strategies
- **LogAgent** — structured JSON logging (structlog) with rotating file output

---

## Project Structure

```
ai-test-automation/
│
├── agents/                        # Agent system prompts (.md files)
│   ├── orchestrator.md
│   ├── lead_agent.md
│   ├── ui_agent.md
│   ├── api_agent.md
│   ├── db_agent.md
│   ├── test_script_agent.md
│   ├── review_agent.md
│   ├── report_agent.md
│   ├── log_agent.md
│   └── cicd_agent.md
│
├── framework/
│   ├── core/
│   │   ├── config.py              # YAML config loader + env var overrides
│   │   ├── exceptions.py          # Custom exception hierarchy
│   │   ├── llm_provider.py        # LLM abstraction (OpenRouter)
│   │   ├── vector_store.py        # ChromaDB wrapper
│   │   ├── message_bus.py         # In-process event bus
│   │   └── base_agent.py          # BaseAgent ABC + PipelineContext model
│   │
│   ├── agents/                    # Agent implementations
│   │   ├── lead_agent.py
│   │   ├── ui_agent.py
│   │   ├── api_agent.py
│   │   ├── db_agent.py
│   │   ├── test_script_agent.py
│   │   ├── review_agent.py
│   │   ├── report_agent.py
│   │   ├── log_agent.py
│   │   └── cicd_agent.py
│   │
│   ├── orchestrator/
│   │   └── orchestrator.py        # Pipeline coordinator
│   │
│   ├── planner/
│   │   └── task_planner.py        # Intent → task decomposition
│   │
│   └── integrations/
│       └── jira_connector.py      # Jira read + write (toggle via config)
│
├── tests/                         # Generated test scripts land here
├── pages/                         # Generated Page Object Models
├── configs/
│   └── config.yaml                # Master configuration file
├── data/                          # Test data files
├── reports/                       # Allure results + JSON summaries
├── logs/                          # Structured JSON logs
├── vector_store/                  # ChromaDB persistence
│
├── cli.py                         # `atf` CLI entry point
├── requirements.txt
├── pytest.ini
├── .env.example                   # Environment variable template
└── .gitignore
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| LLM | [OpenRouter](https://openrouter.ai) (OpenAI-compatible, 100+ models) |
| UI Testing | Playwright + pytest-playwright |
| API Testing | requests |
| DB Testing | SQLAlchemy |
| Test Runner | Pytest |
| Reporting | Allure |
| Vector DB | ChromaDB (persistent) |
| Jira | `jira` library (read + optional write-back) |
| Logging | structlog (JSON, rotating file) |
| CLI | Click + Rich |
| Retry | tenacity |

---

## Quick Start

### 1. Clone and set up environment

```bash
git clone <repo-url>
cd ai-test-automation

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure environment variables

```bash
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux
```

Edit `.env`:

```env
OPENROUTER_API_KEY=sk-or-v1-your-key-here

# Jira (optional)
JIRA_BASE_URL=https://your-company.atlassian.net
JIRA_EMAIL=your-email@company.com
JIRA_API_TOKEN=your-api-token
JIRA_PROJECT_KEY=QA
```

### 4. Choose your LLM model

Open `configs/config.yaml` and set:

```yaml
llm:
  model: openai/gpt-4o-mini       # fast + cheap
  # model: anthropic/claude-3-haiku  # great for code gen
  # model: google/gemini-flash-1.5   # very fast
```

### 5. Run ATF

```bash
# Generate UI tests from a prompt
python cli.py run "Test login functionality with valid and invalid credentials"

# Generate API tests and execute them
python cli.py run "Validate the /api/v1/users endpoint returns correct schema" --execute

# Generate tests from a Jira ticket
python cli.py run --jira QA-123

# Generate tests + run + create CI/CD pipeline
python cli.py run --jira QA-123 --execute --cicd

# View the Allure report
allure serve reports/allure-results
```

---

## Configuration

All settings live in `configs/config.yaml`. Environment variables always override config file values.

```yaml
llm:
  provider: openrouter
  model: openai/gpt-4o-mini     # swap to any OpenRouter model
  temperature: 0.1
  max_tokens: 4096

execution:
  browser: chromium             # chromium | firefox | webkit
  headless: true
  timeout_ms: 30000
  output_dir: ./tests

reporting:
  allure: true
  attach_screenshots: true
  attach_logs: true
  attach_api_responses: true
  report_dir: ./reports

vector_store:
  provider: chroma
  persist_directory: ./vector_store

jira:
  enabled: true
  write_back: false             # false = read-only | true = read + post results back

logging:
  level: INFO                   # DEBUG | INFO | WARNING | ERROR
  format: json                  # json | console
  output_dir: ./logs

cicd:
  provider: github_actions      # github_actions | gitlab_ci
  output_dir: ./.github/workflows
```

---

## CLI Usage

```
Usage: cli.py [OPTIONS] COMMAND [ARGS]...

  Agentic TestGen Framework (ATF) — AI-driven test generation.

Commands:
  run           Generate tests from a prompt or Jira ticket
  generate-cicd Generate a CI/CD pipeline config for existing tests
```

### `atf run`

```
Usage: cli.py run [OPTIONS] [PROMPT]

Options:
  --jira TICKET_ID    Jira ticket to use as input (e.g. QA-123)
  --execute           Run generated tests with pytest
  --cicd              Generate CI/CD pipeline YAML after generation
  --config PATH       Path to a custom config.yaml
```

**Examples:**

```bash
# Natural language prompt
python cli.py run "Test user registration with valid and invalid email formats"

# From Jira ticket
python cli.py run --jira QA-456

# Hybrid: enrich Jira ticket with extra context
python cli.py run "Also test the remember-me checkbox" --jira QA-456

# Full pipeline: generate + execute + CI/CD
python cli.py run "Test checkout flow" --execute --cicd

# Use a different config
python cli.py run "Test login" --config configs/staging.yaml
```

### `atf generate-cicd`

```bash
python cli.py generate-cicd
# Generates: .github/workflows/atf-tests.yml
```

---

## Agent Reference

| Agent | File | Responsibility |
|---|---|---|
| **Orchestrator** | `framework/orchestrator/orchestrator.py` | Pipeline coordinator, DI container |
| **Lead Agent** | `framework/agents/lead_agent.py` | Intent detection + test type classification |
| **Task Planner** | `framework/planner/task_planner.py` | Decomposes intent into ordered tasks |
| **UI Agent** | `framework/agents/ui_agent.py` | Playwright scenario + locator generation |
| **API Agent** | `framework/agents/api_agent.py` | REST/GraphQL test scenario generation |
| **DB Agent** | `framework/agents/db_agent.py` | SQL validation scenario generation |
| **Test Script Agent** | `framework/agents/test_script_agent.py` | Generates runnable pytest scripts |
| **Review Agent** | `framework/agents/review_agent.py` | Quality gate — syntax, best practices, flakiness |
| **Report Agent** | `framework/agents/report_agent.py` | Allure integration + JSON summary |
| **Log Agent** | `framework/agents/log_agent.py` | Structured logging configuration |
| **CI/CD Agent** | `framework/agents/cicd_agent.py` | GitHub Actions / GitLab CI YAML generation |

Each agent loads its system prompt from the corresponding `.md` file in `agents/`.

**To customise an agent's behaviour** — edit the `.md` file. No Python changes needed.

---

## Jira Integration

### Read-only (default)

```yaml
# config.yaml
jira:
  enabled: true
  write_back: false
```

```bash
python cli.py run --jira QA-123
```

ATF fetches the ticket summary, description, and acceptance criteria, then uses them to generate tests.

### Read + Write

```yaml
# config.yaml
jira:
  enabled: true
  write_back: true   # Posts test results as a comment on the ticket
```

When `write_back: true`, ATF posts a test result comment on the Jira ticket after execution:

```
✅ ATF Automated Test Results

Status: PASSED
Total: 5 | Passed: 5 | Failed: 0
Pass Rate: 100%

_Generated by Agentic TestGen Framework (ATF)_
```

---

## CI/CD

Generate a pipeline config:

```bash
python cli.py generate-cicd
# Output: .github/workflows/atf-tests.yml
```

The generated pipeline:
- Installs Python 3.12 + dependencies
- Installs Playwright browsers
- Runs `pytest tests/` with Allure output
- Uploads Allure results as artifacts (on pass **and** fail)
- Reads `BASE_URL` and `OPENROUTER_API_KEY` from CI secrets

To switch to GitLab CI:

```yaml
# config.yaml
cicd:
  provider: gitlab_ci
```

---

## Roadmap

| Version | Features |
|---|---|
| **V1** ✅ | Prompt → UI/API test generation, Review Agent, Execution + Allure, Jira read+write, CLI |
| **V2** | DB validation, vector memory reuse, CI/CD auto-generation, batch Jira project processing |
| **V3** | Self-healing tests, intelligent retry strategies, performance testing, multi-agent debate |

---

## Contributing

1. Add a new agent by:
   - Creating `agents/<name>.md` with the system prompt
   - Creating `framework/agents/<name>.py` subclassing `BaseAgent`
   - Registering it in `framework/orchestrator/orchestrator.py`

2. Add a new LLM provider by:
   - Subclassing `LLMProvider` in `framework/core/llm_provider.py`
   - Adding a branch to `create_llm_provider()`

---

## License

MIT
