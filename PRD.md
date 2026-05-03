# Agentic TestGen Framework (ATF) - Product Requirements Document

---

## 1. Overview

### 1.1 Objective

Build an **agent-driven automation testing platform** that:

* Interprets natural language or structured prompts
* Identifies test type (UI/API/DB)
* Generates Playwright + Pytest test scripts
* Executes tests and produces Allure reports
* Integrates with CI/CD pipelines
* Supports multi-LLM and vector memory

---

## 2. Goals

### Primary Goals

* Generate UI/API/DB test scripts from prompts
* Enable autonomous execution pipeline
* Modular agent-driven architecture via `.md` files

### Secondary Goals

* Reduce manual scripting effort
* Standardize automation practices
* Enable future AI learning capabilities

---

## 3. Non-Goals (V1 Scope Control)

* No self-healing automation
* No visual/image-based testing
* No performance testing
* No auto-fixing flaky tests
* No multi-agent debate system

---

## 4. User Inputs

### 4.1 Natural Language Prompt

Example:
Test login functionality with valid and invalid credentials

### 4.2 Structured Input

```yaml
source: jira
ticket_id: QA-123
test_type: ui
```

### 4.3 Hybrid Input

Fetch test cases from TestRail for login module and generate API tests

---

## 5. Core Capability: Test Type Detection

### Responsible Agent: Lead Agent

### Supported Types:

* UI (Playwright)
* API (requests)
* DB (SQL validation)

### Initial Logic:

* Keyword-based classification
* Few-shot learning
* Extendable to embedding-based classification

---

## 6. Architecture

### High-Level Flow

User Prompt
↓
Orchestrator Agent
↓
Lead Agent (Intent + Classification)
↓
Task Planner
↓
Specialized Agents (UI / API / DB)
↓
Test Script Agent
↓
Review Agent
↓
Execution Engine (pytest + Playwright)
↓
Report Agent (Allure)
↓
CI/CD Agent

---

## 7. Agent Definitions

All agents are defined as markdown files under `/agents`.

---

### 7.1 Orchestrator Agent

* Entry point of system
* Routes workflow between agents

---

### 7.2 Lead Agent

* Detects intent
* Classifies test type

**Output Example:**

```json
{
  "test_type": "ui",
  "source": "prompt",
  "tasks": []
}
```

---

### 7.3 UI Agent

* Uses Playwright for DOM understanding
* Suggests locators
* Maps elements to POM

---

### 7.4 API Agent

* Generates API test scenarios
* Handles request/response validation

---

### 7.5 DB Agent

* Generates SQL queries
* Validates backend data

---

### 7.6 Test Script Agent

* Generates pytest-compatible scripts
* Uses Playwright (UI) and requests (API)

---

### 7.7 Review Agent

Validates:

* Syntax correctness
* Playwright best practices
* Flaky test detection

---

### 7.8 Report Agent

* Integrates Allure reporting
* Generates execution summaries

---

### 7.9 Log Agent

* Centralized structured logging
* Tracks agent decisions

---

### 7.10 CI/CD Agent

* Generates pipeline configurations
* Supports GitHub Actions and GitLab CI

---

## 8. Project Structure

```
agentic_test_framework/
│
├── agents/
│   ├── orchestrator.md
│   ├── lead_agent.md
│   ├── ui_agent.md
│   ├── api_agent.md
│   ├── db_agent.md
│   ├── test_script_agent.md
│   ├── review_agent.md
│   ├── report_agent.md
│   ├── log_agent.md
│   ├── cicd_agent.md
│
├── framework/
│   ├── core/
│   ├── orchestrator/
│   ├── planner/
│
├── tests/
├── pages/
├── configs/
├── data/
├── reports/
├── logs/
├── vector_store/
```

---

## 9. Tech Stack

* Python
* Pytest
* Playwright
* Requests (API testing)
* Allure (reporting)
* YAML / JSON (config)

### LLM Support

* OpenAI (default)
* Local models (Ollama, etc.)
* Pluggable architecture

### Vector DB

* FAISS or Chroma

---

## 10. LLM Abstraction Layer

```python
class LLMProvider:
    def generate(prompt: str) -> str:
        pass
```

---

## 11. Few-Shot Learning (Agent Level)

Each agent must include examples:

Prompt: Test login page
Output: UI

Prompt: Validate user API response
Output: API

---

## 12. Execution Engine

* Pytest runner
* Playwright integration
* Supports future parallel execution

---

## 13. Review Rules

* Avoid hardcoded waits
* Use stable selectors
* Ensure assertions exist
* Suggest retry strategies

---

## 14. Reporting

* Allure integration
* Attach logs, screenshots, API responses

---

## 15. CI/CD

### Supported

* GitHub Actions
* GitLab CI

### Output

* Auto-generated YAML pipeline

---

## 16. Memory Layer (Vector DB)

### Stores

* Prompts
* Generated tests
* Locator strategies

### Purpose

* Improve test generation
* Reuse patterns

---

## 17. Configuration

```yaml
llm:
  provider: openai

execution:
  browser: chromium

reporting:
  allure: true
```

---

## 18. Risks & Mitigation

| Risk                  | Mitigation         |
| --------------------- | ------------------ |
| Hallucinated locators | Use DOM grounding  |
| Flaky tests           | Review agent       |
| High LLM cost         | Cache responses    |
| Slow execution        | Event-driven model |

---

## 19. Roadmap

### V1

* Prompt → UI/API test generation
* Review agent
* Execution + Allure

### V2

* DB validation
* Memory integration
* CI/CD generation

### V3

* Self-healing
* Intelligent retries
* Optimization

---

## 20. Success Metrics

* Test generation accuracy
* Execution success rate
* Reduction in manual effort
* Review effectiveness

---
