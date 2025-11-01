# Development Setup

Local development without Docker.

---

## Prerequisites

- Python 3.10+
- pip
- virtualenv

---

## Setup Steps

### 1. Clone Repository

```bash
git clone https://github.com/Xe138/AI-Trader-Server.git
cd AI-Trader-Server
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 5. Start MCP Services

```bash
cd agent_tools
python start_mcp_services.py &
cd ..
```

### 6. Start API Server

```bash
python -m uvicorn api.main:app --reload --port 8080
```

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Project Structure

See [CLAUDE.md](../../CLAUDE.md) for complete project structure.
