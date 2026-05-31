# LLM Deployment — Qwen SQL Generator on Modal
 
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![Modal](https://img.shields.io/badge/Platform-Modal-purple.svg)](https://modal.com)
[![HuggingFace](https://img.shields.io/badge/HuggingFace-Model%20on%20HF%20Hub-brightgreen)](https://huggingface.co/faltooz123/qwen1.5-sql-qlora-spider)
 
**Serverless deployment of a fine-tuned Text-to-SQL model on Modal GPU infrastructure.**
 
[Quick Start](#quick-start) • [Deployment](#deployment) • [Client Usage](#client-usage) • [Monitoring](#monitoring)
 
---
 
> **Note:** This repository is a **deployment plan and reference implementation**
> for a Text-to-SQL LLM application. The code demonstrates how the deployment
> would be structured and executed — it has not been deployed to live
> infrastructure. This is intentional: the project objective is to demonstrate
> understanding of production LLM deployment patterns, platform selection,
> cost analysis, and monitoring strategy without incurring actual cloud costs.
> All scripts are written to be fully functional and ready to deploy by
> following the instructions in this README.
 
---

## TL;DR

This repository contains the deployment infrastructure for `faltooz123/qwen1.5-sql-qlora-spider` — a Qwen1.5-1.8B model fine-tuned for Text-to-SQL generation. The model is deployed as a serverless API on Modal, allowing business users to convert natural language questions into SQL queries.

**Related:** [Module 1 — Fine-Tuning Repository](https://github.com/pamuarun/LLM_FINE_TUNING)

---

>  **📌 Note:** This repository is a **deployment plan and reference implementation**
> for a Text-to-SQL LLM application. The code demonstrates how the deployment
> *would* be structured and executed it has not been deployed to live
> infrastructure. This is intentional: the project objective is to demonstrate
> understanding of production LLM deployment patterns, platform selection,
> cost analysis, and monitoring strategy without incurring actual cloud costs.
> All scripts are written to be fully functional and ready to deploy by
> following the instructions in this README.

## Repository Structure

```
LLM_DEPLOYMENT/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── deploy/
│   └── modal_deploy.py          # Modal serverless deployment script
├── client/
│   ├── client.py                # HTTP client for the deployed API
│   └── test_requests.py         # Test suite (10 SQL + 3 security tests)
└── config/
    └── model_config.yaml        # Model and deployment configuration
```

---

## Deployment Overview

| Property | Value |
|---|---|
| Model | Qwen/Qwen1.5-1.8B-Chat + LoRA adapter |
| Adapter | faltooz123/qwen1.5-sql-qlora-spider |
| Platform | Modal (Serverless GPU) |
| GPU | NVIDIA A10G (24GB VRAM) |
| Quantization | 4-bit NF4 (QLoRA) |
| Est. latency | < 2 seconds (warm) |
| Est. cost | ~$22/month at 25K requests |
| Scales to zero | ✅ Yes |

---

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/pamuarun/LLM_DEPLOYMENT
cd LLM_DEPLOYMENT
```

### 2. Create Virtual Environment

```bash
python -m venv deploy_env
deploy_env\Scripts\activate   # Windows
# source deploy_env/bin/activate  # Linux/macOS
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Up Accounts

You need free accounts on:
- **Modal**: https://modal.com (free $30/month credits)
- **Hugging Face**: https://huggingface.co (free)
- **LangFuse**: https://langfuse.com (free tier)

### 5. Authenticate

```bash
# Modal CLI login
modal token new

# Hugging Face login
huggingface-cli login

# Set environment variables
cp .env.example .env
# Edit .env with your actual keys
```

---

## Environment Variables

Create a `.env` file in the project root:

```bash
# Hugging Face
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx

# SQL API Key (create your own random string)
SQL_API_KEY=sk-sql-xxxxxxxxxxxxxxxxxxxx

# Modal endpoint URL (get this after deploying)
SQL_ENDPOINT_URL=https://your-app-name.modal.run

# LangFuse Observability
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxxxxxxxxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxxxxxxxxxxxxxx
LANGFUSE_HOST=https://cloud.langfuse.com
```

Set Modal secrets:
```bash
modal secret create sql-api-secrets \
  HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx \
  SQL_API_KEY=sk-sql-xxxxxxxxxxxxxxxxxxxx \
  LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxxxxxxxxxxxxxx \
  LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxxxxxxxxxxxxxx
```

---

## Deployment

### Test Locally First

```bash
# Run local test (no GPU needed)
modal run deploy/modal_deploy.py
```

### Deploy to Modal

```bash
# Deploy the serverless endpoint
modal deploy deploy/modal_deploy.py
```

After deploying, Modal will print your endpoint URL:
```
✓ Created web endpoint: https://your-app-name--sql-endpoint.modal.run
```

Copy this URL and set it as `SQL_ENDPOINT_URL` in your `.env` file.

### Serve (Development Mode)

```bash
# Live reload during development
modal serve deploy/modal_deploy.py
```

---

## Client Usage

### Basic Usage

```python
from client.client import SQLGeneratorClient

client = SQLGeneratorClient(
    endpoint_url = "https://your-modal-endpoint.modal.run",
    api_key      = "sk-sql-xxxxxxxxxxxxxxxxxxxx"
)

result = client.generate_sql(
    question = "How many singers do we have?",
    db_id    = "concert_singer"
)

print(result["sql"])
# Output: SELECT count(*) FROM singer;
```

### Interactive Mode

```bash
python client/client.py
```

### Run Full Test Suite

```bash
python client/test_requests.py
```

Expected output:
```
TEST SUMMARY
============================================================
  Total tests     : 10
  Passed          : 6 (60.0%)
  Failed          : 4 (40.0%)
  Avg latency     : 1842ms
  Security tests  : 3/3 passed
============================================================
```

---

## API Reference

### POST `/`

Generate a SQL query from a natural language question.

**Request:**
```json
{
    "question": "How many singers do we have?",
    "db_id": "concert_singer",
    "api_key": "sk-sql-xxxxxxxxxxxxxxxxxxxx"
}
```

**Response (success):**
```json
{
    "success": true,
    "sql": "SELECT count(*) FROM singer;",
    "question": "How many singers do we have?",
    "db_id": "concert_singer",
    "latency_ms": 1823,
    "error": null
}
```

**Response (error):**
```json
{
    "success": false,
    "sql": null,
    "error": "Unauthorized: invalid or missing API key",
    "question": "...",
    "db_id": "..."
}
```

**Status Codes:**
| Code | Meaning |
|---|---|
| 200 | Success (check `success` field) |
| 401 | Unauthorized — invalid API key |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

---

## Monitoring

### Modal Dashboard

View container health, GPU utilization, and scaling events at:
```
https://modal.com/apps/your-app-name
```

### LangFuse Traces

Every request is traced in LangFuse with:
- Input question and database name
- Generated SQL output
- Response latency
- Token count

Access at: https://cloud.langfuse.com

### Alert Thresholds

| Metric | Warning | Critical |
|---|---|---|
| Latency p50 | > 3s | > 5s |
| Latency p99 | > 8s | > 15s |
| Error rate | > 2% | > 5% |
| Monthly spend | > $40 | > $60 |

---

## Cost Estimate

| Component | Monthly Cost |
|---|---|
| Compute (A10G GPU) | ~$15.40 |
| Container idle time | ~$4.84 |
| Storage | ~$2.00 |
| Network | ~$0.50 |
| **Total** | **~$22.74** |

**Cost per 1,000 requests: ~$0.62**

*Modal provides $30/month free credits — this deployment runs within free tier for the first month.*

---

## Security

- ✅ API key authentication on every request
- ✅ Rate limiting (60 req/min standard, 300 premium)
- ✅ Input validation and prompt injection prevention
- ✅ SQL injection protection on database ID field
- ✅ Input length limits (500 chars max)
- ✅ Log encryption at rest (AES-256)
- ✅ 30-day log retention policy

---

## Links

| Resource | Link |
|---|---|
| 🤗 Fine-Tuned Model | [faltooz123/qwen1.5-sql-qlora-spider](https://huggingface.co/faltooz123/qwen1.5-sql-qlora-spider) |
| 📦 Module 1 Repo | [pamuarun/LLM_FINE_TUNING](https://github.com/pamuarun/LLM_FINE_TUNING) |
| 🚀 Modal Docs | [modal.com/docs](https://modal.com/docs) |
| 📊 LangFuse | [langfuse.com](https://langfuse.com) |
| 📂 Spider Dataset | [xlangai/spider](https://huggingface.co/datasets/xlangai/spider) |

---

## Author

**Arun Teja Pamu** — LLM Deployment Capstone Project

- 🤗 HuggingFace: [@faltooz123](https://huggingface.co/faltooz123)
- 💻 GitHub: [@pamuarun](https://github.com/pamuarun)
