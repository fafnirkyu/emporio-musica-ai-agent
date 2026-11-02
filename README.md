# Empório da Música AI Agent

A command-line customer-service agent for a fictional Brazilian music store. Amy answers questions about the product catalog, stock, prices, promotions, orders, and store policies while keeping structured data queries separate from document retrieval.

This project was developed as a technical assessment for an AI Engineer position.

## Features

- Natural-language product searches by name, category, availability, and maximum price.
- Exact product lookup with clear out-of-stock warnings.
- Active promotion lookup with prices calculated in integer cents.
- Order-status queries protected by local email verification.
- Store-policy retrieval from the supplied PDF.
- Multi-turn conversation memory for the current session.
- Out-of-scope request handling without exposing unnecessary tools.
- Automated tests and a live evaluation harness.

Amy communicates in Brazilian Portuguese because the supplied catalog, policies, example questions, and retail context are Brazilian. The repository documentation is written in English to follow the submission instructions.

## Architecture

```text
Customer
   |
   v
Python CLI
   |
   v
StoreAgent (Gemini 2.5 Flash)
   |
   v
Allowlisted ToolDispatcher
   |-------------------------------|
   |                               |
   v                               v
SQLite structured tools        TF-IDF policy retriever
products, promotions,          supplied policy PDF,
orders, and customers          best page plus neighbors
```

Gemini decides whether a request needs structured store data, policy context, or no tool. Tool execution remains under application control: the model can only request the functions exposed in the allowlist, and the dispatcher validates the tool name before execution.

For order lookups, Gemini receives only the numeric order identifier. The verification email is collected by local application code and is not added to the model's tool arguments or conversation history.

## Technical decisions

### Hybrid function calling and retrieval

Structured facts such as prices, stock quantities, promotions, and order status come from SQLite tools. Store policies are retrieved from the PDF with local TF-IDF search. This avoids asking the language model to calculate or invent exact business data while still allowing natural customer conversations.

### Gemini 2.5 Flash

Gemini 2.5 Flash provides multilingual function calling with low latency and a free development tier. The model is configurable through `GEMINI_MODEL`, so another compatible Gemini model can be selected without changing the application code.

### In-memory SQLite

The supplied CSV files are loaded into a fresh in-memory SQLite database at startup. The dataset is small and read-only, so rebuilding it keeps setup simple and avoids committing a generated database file. SQLite foreign-key checks are enabled, and monetary values are stored as integer cents to avoid floating-point rounding errors.

### Local policy retrieval

Policy pages are indexed locally with a TF-IDF vectorizer using Portuguese stop words and word n-grams. A query retrieves the best matching page together with the previous and next pages when available. Including neighboring pages preserves rules that cross page boundaries without spending API quota on embeddings.

### Session-only conversation history

Gemini's chat session keeps follow-up questions contextual while the CLI is running. History is intentionally not persisted because the assessment does not require user accounts or long-term conversation storage.

### Command-line interface

The CLI keeps the interaction layer deliberately small so the assessment remains focused on agent behavior, retrieval, data correctness, and tool safety rather than frontend work.

## Data treatment

At startup, Pandas reads the supplied CSV files and prepares their column types before they are inserted into SQLite. The loading process:

- converts prices and order totals to integer cents;
- normalizes missing optional values;
- parses product specifications stored as JSON;
- preserves relationships between categories, products, customers, orders, and order items;
- enables SQLite foreign-key enforcement; and
- evaluates promotion dates and stock availability when tools are called.

The source files remain unchanged under `data/`.

## Requirements

- Python 3.10 or newer
- A Gemini API key

## Setup

Clone the repository and enter its directory:

```bash
git clone https://github.com/fafnirkyu/emporio-musica-ai-agent.git
cd emporio-musica-ai-agent
```

Create and activate a virtual environment.

Windows PowerShell:

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux or macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the runtime dependencies:

```bash
python -m pip install -r requirements.txt
```

Create the local environment file from the example:

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Linux or macOS:

```bash
cp .env.example .env
```

Add the API key to `.env`:

```dotenv
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

The `.env` file is ignored by Git and must not be committed.

## Running the agent

Start the CLI from the repository root:

```bash
python -m app.cli
```

Ask Amy about products, prices, availability, promotions, orders, or store policies. Enter `sair`, `exit`, or `quit` to close the session.

## Tests

Install the development dependencies:

```bash
python -m pip install -r requirements-dev.txt
```

Run the automated test suite:

```bash
python -m pytest -q
```

The suite currently contains 36 tests covering database loading, monetary conversion, product and promotion queries, verified order access, policy retrieval, tool dispatch, function-calling behavior, and privacy boundaries. Gemini calls are mocked in automated tests, so the test suite does not require an API key or consume API quota.

GitHub Actions runs the same suite with Python 3.10 on pushes to `main` and on pull requests targeting `main`.

## Live evaluation

The optional live evaluation harness sends varied scenarios through the real Gemini model and records tool selection, privacy checks, and final answers:

```bash
python scripts/evaluate_agent.py
```

The script waits between scenarios to reduce the chance of exceeding free-tier request-per-minute limits and writes its output to `docs/live-evaluation.txt`. It still depends on the API account's available daily quota, and model responses can vary slightly between runs.

Five successful interactions covering structured retrieval, policy retrieval, local order verification, conversation memory, and scope control are documented in [docs/example-conversations.md](docs/example-conversations.md).

## Project structure

```text
app/
  agent.py       Gemini configuration, tool declarations, and agent loop
  cli.py         Command-line interface and local email prompt
  database.py    CSV loading and in-memory SQLite construction
  policy.py      PDF extraction and TF-IDF policy retrieval
  store.py       Deterministic catalog, promotion, and order operations
data/            Supplied CSV files and store-policy PDF
docs/            Tested example conversations
scripts/         Optional live-agent evaluation harness
tests/           Automated unit and integration-style tests
```

## Limitations

- The CLI requires network access and an available Gemini API quota.
- TF-IDF is lexical retrieval and may miss questions that use vocabulary unrelated to the policy text.
- The SQLite database is rebuilt at startup and does not support persistent updates.
- Conversation history lasts only for the current process.
- Email matching demonstrates an order-privacy boundary but is not production-grade authentication.
- The prototype has no streaming responses, centralized telemetry, or persistent audit log.
- Language-model output is nondeterministic even though tool results are deterministic.

For production use, the next steps would include authenticated customer sessions, a persistent managed database, structured observability, API retry and backoff policies, secret management, and evaluation against a larger labeled dataset.

## AI-assisted development disclosure

OpenAI Codex was used as a pair-programming tool during development. It helped discuss architecture trade-offs, draft portions of the implementation and tests, investigate SDK behavior, review errors, and organize documentation. I made the project decisions, created and reviewed the files, ran the code and tests locally, inspected the supplied data, and validated the agent's answers against the underlying records and policies.

Gemini 2.5 Flash is the runtime model used by Amy and is separate from the development assistance described above.
