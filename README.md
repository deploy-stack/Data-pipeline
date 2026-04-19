# Pre-College Program Matching Pipeline

This is a polished Python pipeline for matching pre-college programs to student profiles. It discovers, extracts, verifies, and matches program data from official sources, storing results in a DuckDB database for easy querying and visualization via Streamlit.

## Features

- **Web Scraping & Discovery**: Uses Firecrawl API to discover and extract program data from official websites.
- **AI-Powered Processing**: Leverages Anthropic Claude for intelligent data normalization and matching.
- **Data Verification**: Implements confidence scoring and field validation.
- **Scalable Architecture**: Parallel processing, caching, and batching for handling 100+ sources.
- **Interactive UI**: Streamlit app for profile input, pipeline execution, and dataset exploration.
- **Persistent Storage**: DuckDB for reliable data storage with SQL querying capabilities.

## Project Structure

```
.
├── agent_tools.py              # Core API clients and utilities
├── app.py                      # Streamlit web interface
├── demo.py                     # CLI entry point for pipeline execution
├── discover.py                 # URL discovery logic
├── extract.py                  # HTML parsing and data extraction
├── firecrawl_agents.py         # Firecrawl integration agents
├── match.py                    # Interest and eligibility matching
├── orchestrator_agent.py       # Pipeline orchestration
├── profile_discovery_agent.py  # Profile-based discovery
├── profile_parser.py           # Student profile parsing
├── program_database.py         # Database operations
├── program_extraction_agent.py # Parallel extraction
├── schema.py                   # Data models and schemas
├── storage_duckdb.py           # DuckDB storage implementation
├── verification_matching_agent.py # Verification logic
├── verify.py                   # Record verification
├── data/                       # Data storage directory
│   ├── demo.duckdb             # DuckDB database
│   └── ...                     # Cached data files
├── tests/                      # Unit tests
├── requirements.txt            # Python dependencies
├── .gitignore                  # Git ignore rules
└── README.md                   # This file
```

## Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd 2026-04-18-build-a-simple-but-polished-python
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   Create a `.env` file in the root directory:
   ```
   FIRECRAWL_API_KEY=your_firecrawl_api_key
   ANTHROPIC_API_KEY=your_anthropic_api_key
   ```

## Usage

### Command Line Pipeline

Run the full pipeline:
```bash
python demo.py
```

With custom parameters:
```bash
python demo.py --batch-size 5 --max-sources 10
```

### Streamlit Web App

Launch the interactive web interface:
```bash
streamlit run app.py
```

This provides:
- Student profile input form
- Pipeline execution controls
- Dataset visualization with complete/incomplete record views
- Real-time progress monitoring

### Querying the Database

View stored programs:
```bash
python -c "import duckdb; conn = duckdb.connect('data/demo.duckdb'); print(conn.execute('SELECT program_name, provider, cost FROM programs').fetchall())"
```

## API Keys

- **Firecrawl API**: Required for web scraping. Get your key from [firecrawl.dev](https://firecrawl.dev).
- **Anthropic API**: Required for AI processing. Get your key from [anthropic.com](https://anthropic.com).

## Development

Run tests:
```bash
python -m pytest tests/
```

## License

This project is for demonstration purposes.
python demo.py --limit 5
```

Expected output:

- A list of extracted programs
- Verified key fields and completeness scores
- Top matches for this student profile:
  - grade: 11
  - interests: computer science, AI, engineering
  - preferred modality: online
  - budget max: $4,000

## Refresh From Official Pages

Install dependencies:

```bash
pip install -r requirements.txt
```

Fetch official pages and regenerate `data/programs.json` and `data/programs.csv`:

```bash
python demo.py --refresh
```

The refresh path is deliberately lightweight. Real university pages vary a lot, so `extract.py` combines generic text extraction with a small `PROGRAM_HINTS` map for known seed URLs. That keeps the demo readable while still showing how the pipeline can grow.

Refresh mode uses a polite fetch helper with robots.txt checks, a Vantion demo user agent, and randomized delay between requests.

## Streamlit Preview

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app collects a student profile, runs a three-agent pipeline, then shows ranked recommendations and the structured dataset.

The Firecrawl path does not use the curated school list. It searches the open web from the student profile and then extracts/validates matching program pages.

It uses:

- `PipelineOrchestratorAgent` in `orchestrator_agent.py`: runs the handoffs between agents.
- `ProfileDiscoveryAgent` in `profile_discovery_agent.py`: turns grade, interests, modality, location, and budget into Firecrawl web search queries.
- `ProgramExtractionAgent` in `program_extraction_agent.py`: uses Firecrawl `/scrape` with markdown plus JSON schema extraction to pull program fields from discovered pages.
- `VerificationMatchingAgent` in `verification_matching_agent.py`: verifies deadline, eligibility, cost, confidence, location fit, stores records, and builds the match-ready index.
- `agent_tools.py`: contains the actual tools each agent uses, including Firecrawl search/scrape tools, verification, matching, snapshot, and storage tools.

If Firecrawl is disabled or `FIRECRAWL_API_KEY` is missing, the app falls back to the bundled verified snapshot so the demo still works offline.

Claude Haiku 4.5 can be used for lightweight agent intelligence. Add one of these to `.env`:

```bash
ANTHROPIC_API_KEY=your_key
# or
CLAUDE_API_KEY=your_key
```

The project uses `claude-haiku-4-5-20251001` for query planning, extracted-record normalization, and short verification notes. If the Claude key is missing, those steps use deterministic fallbacks.

For CLI:

```bash
python demo.py --agentic
```

## Quality Checks

```bash
python storage_duckdb.py
```

This loads `data/programs.csv` into `data/demo.duckdb` and prints total programs, missing deadline count, and average confidence.

## What This Demonstrates

- Discovery: `discover.py` saves a deduplicated list of official program URLs.
- Extraction: `extract.py` converts page text into structured program records.
- Verification: `verify.py` checks whether eligibility, deadline, modality/location, and cost are explicitly supported by page text.
- Storage: outputs are saved to `data/programs.json` and `data/programs.csv`.
- Matching: `match.py` ranks programs by eligibility, subject fit, modality, budget, and deadline completeness.

## Notes For Interviewers

This is not a production crawler. It is a clear, extensible agentic data-pipeline demo: each stage has a job, saves an artifact, and produces data that a counselor-style product can use for personalized recommendations and planning.
