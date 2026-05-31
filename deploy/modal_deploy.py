"""
modal_deploy.py
---------------
Serverless deployment of the fine-tuned Qwen1.5-1.8B Text-to-SQL model
on Modal GPU infrastructure.

Model: faltooz123/qwen1.5-sql-qlora-spider
Base:  Qwen/Qwen1.5-1.8B-Chat
GPU:   NVIDIA A10G (24GB VRAM)

Usage:
    modal deploy deploy/modal_deploy.py
    modal serve deploy/modal_deploy.py   # for local testing
"""

import os
import modal

# ── Modal App Definition ───────────────────────────────────────────────────────
app = modal.App("qwen-sql-qlora")

# ── Container Image ────────────────────────────────────────────────────────────
# Build a container image with all required dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch==2.4.1",
        "transformers==4.44.2",
        "peft==0.12.0",
        "bitsandbytes==0.43.3",
        "accelerate==0.34.2",
        "huggingface-hub==0.25.1",
        "sentencepiece==0.2.0",
        "langfuse==2.36.0",
        "fastapi==0.115.0",
        "sqlparse==0.5.1",
    )
)

# ── Model Volume (cache model weights between runs) ────────────────────────────
volume = modal.Volume.from_name("qwen-sql-model-cache", create_if_missing=True)
MODEL_CACHE_DIR = "/model-cache"

# ── Secrets ───────────────────────────────────────────────────────────────────
# Set these via: modal secret create sql-api-secrets
secrets = [
    modal.Secret.from_name("sql-api-secrets"),  # HF_TOKEN, LANGFUSE keys, API_KEY
]

# ── Model Configuration ────────────────────────────────────────────────────────
BASE_MODEL_ID   = "Qwen/Qwen1.5-1.8B-Chat"
ADAPTER_ID      = "faltooz123/qwen1.5-sql-qlora-spider"
MAX_NEW_TOKENS  = 128
MAX_INPUT_CHARS = 500


# ── Input Validation ──────────────────────────────────────────────────────────
def validate_input(question: str, db_id: str) -> tuple[bool, str]:
    """
    Validate and sanitize user inputs to prevent prompt injection.
    Returns (is_valid, error_message).
    """
    # Block control tokens
    blocked_tokens = [
        "<|im_start|>", "<|im_end|>",
        "system\n", "assistant\n",
        "IGNORE", "ignore previous",
    ]
    for token in blocked_tokens:
        if token.lower() in question.lower():
            return False, f"Invalid input: contains blocked token '{token}'"

    # Block excessive length
    if len(question) > MAX_INPUT_CHARS:
        return False, f"Question exceeds maximum length of {MAX_INPUT_CHARS} characters"

    # Block empty inputs
    if not question.strip():
        return False, "Question cannot be empty"

    if not db_id.strip():
        return False, "Database ID cannot be empty"

    # Block SQL injection in db_id
    dangerous = [";", "--", "DROP", "DELETE", "INSERT", "UPDATE"]
    for pattern in dangerous:
        if pattern.upper() in db_id.upper():
            return False, f"Invalid database ID: contains dangerous pattern '{pattern}'"

    return True, ""


# ── SQL Cleaning ──────────────────────────────────────────────────────────────
def clean_sql_output(sql: str) -> str:
    """
    Clean and normalize the generated SQL output.
    Removes extra text, Chinese characters, and normalizes whitespace.
    """
    # Stop at end token
    sql = sql.split("<|im_end|>")[0].strip()

    # Stop at double newline
    sql = sql.split("\n\n")[0].strip()

    # Take only first SQL statement
    if ";" in sql:
        sql = sql.split(";")[0].strip() + ";"

    # Remove non-ASCII characters (e.g. Chinese text)
    sql = "".join(char for char in sql if ord(char) < 128).strip()

    # Normalize whitespace
    sql = " ".join(sql.split())

    return sql


# ── Modal Class (GPU Inference) ───────────────────────────────────────────────
@app.cls(
    image=image,
    gpu="A10G",                          # NVIDIA A10G — 24GB VRAM
    secrets=secrets,
    volumes={MODEL_CACHE_DIR: volume},
    timeout=300,                         # 5 min max per request
    container_idle_timeout=120,          # Scale to zero after 2 min idle
    allow_concurrent_inputs=1,           # One request per container
)
class SQLGenerator:

    @modal.enter()
    def load_model(self):
        """
        Load the model once when the container starts.
        This runs only on cold start — subsequent requests reuse the loaded model.
        """
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
        from peft import PeftModel
        from huggingface_hub import snapshot_download

        print("Container starting — loading model...")

        hf_token = os.environ.get("HF_TOKEN")

        # Download base model to volume cache
        print(f"Loading base model: {BASE_MODEL_ID}")
        base_model_path = os.path.join(MODEL_CACHE_DIR, "base_model")
        if not os.path.exists(base_model_path):
            snapshot_download(
                BASE_MODEL_ID,
                local_dir=base_model_path,
                token=hf_token,
            )

        # Download LoRA adapter to volume cache
        print(f"Loading LoRA adapter: {ADAPTER_ID}")
        adapter_path = os.path.join(MODEL_CACHE_DIR, "adapter")
        if not os.path.exists(adapter_path):
            snapshot_download(
                ADAPTER_ID,
                local_dir=adapter_path,
                token=hf_token,
            )

        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            base_model_path,
            trust_remote_code=True,
        )
        self.tokenizer.pad_token    = self.tokenizer.eos_token
        self.tokenizer.padding_side = "right"

        # Load base model in 4-bit
        bnb_config = BitsAndBytesConfig(
            load_in_4bit              = True,
            bnb_4bit_quant_type       = "nf4",
            bnb_4bit_compute_dtype    = torch.float16,
            bnb_4bit_use_double_quant = True,
        )

        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_path,
            quantization_config = bnb_config,
            device_map          = {"": 0},
            trust_remote_code   = True,
        )

        # Load LoRA adapter on top of base model
        self.model = PeftModel.from_pretrained(base_model, adapter_path)
        self.model.eval()

        print("Model loaded successfully!")

    @modal.method()
    def generate(self, question: str, db_id: str) -> dict:
        """
        Generate a SQL query for the given question and database.

        Args:
            question: Natural language question (e.g. "How many users do we have?")
            db_id:    Database identifier (e.g. "users_db")

        Returns:
            dict with keys: sql, question, db_id, success, error
        """
        import torch
        import time

        start_time = time.time()

        # Validate input
        is_valid, error_msg = validate_input(question, db_id)
        if not is_valid:
            return {
                "success"  : False,
                "sql"      : None,
                "question" : question,
                "db_id"    : db_id,
                "error"    : error_msg,
                "latency_ms": 0,
            }

        # Build prompt
        prompt = (
            "<|im_start|>system\n"
            "You are an expert SQL assistant that converts natural language "
            "questions into accurate SQL queries.<|im_end|>\n"
            "<|im_start|>user\n"
            f"You are an expert SQL assistant. Given a natural language question "
            f"and a database name, write the correct SQL query.\n\n"
            f"Database: {db_id}\n"
            f"Question: {question}\n\n"
            f"Write only the SQL query, nothing else.<|im_end|>\n"
            "<|im_start|>assistant\n"
        )

        # Tokenize
        inputs = self.tokenizer(
            prompt,
            return_tensors = "pt",
            truncation     = True,
            max_length     = 512,
        ).to("cuda")

        # Generate
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens = MAX_NEW_TOKENS,
                do_sample      = False,
                temperature    = 1.0,
                pad_token_id   = self.tokenizer.eos_token_id,
                eos_token_id   = self.tokenizer.eos_token_id,
            )

        # Decode
        generated = outputs[0][inputs["input_ids"].shape[1]:]
        raw_sql   = self.tokenizer.decode(generated, skip_special_tokens=True)
        clean_sql = clean_sql_output(raw_sql)

        latency_ms = int((time.time() - start_time) * 1000)

        return {
            "success"    : True,
            "sql"        : clean_sql,
            "question"   : question,
            "db_id"      : db_id,
            "error"      : None,
            "latency_ms" : latency_ms,
        }


# ── FastAPI Web Endpoint ──────────────────────────────────────────────────────
@app.function(
    image=image,
    secrets=secrets,
)
@modal.web_endpoint(method="POST")
def sql_endpoint(request: dict) -> dict:
    """
    HTTP POST endpoint for SQL generation.

    Request body:
        {
            "question": "How many users do we have?",
            "db_id": "users_db",
            "api_key": "sk-sql-xxxx"
        }

    Response:
        {
            "success": true,
            "sql": "SELECT COUNT(*) FROM users;",
            "question": "How many users do we have?",
            "db_id": "users_db",
            "latency_ms": 1234,
            "error": null
        }
    """
    # API key authentication
    expected_key = os.environ.get("SQL_API_KEY", "")
    provided_key = request.get("api_key", "")

    if not provided_key or provided_key != expected_key:
        return {
            "success": False,
            "sql"    : None,
            "error"  : "Unauthorized: invalid or missing API key",
        }

    question = request.get("question", "").strip()
    db_id    = request.get("db_id", "").strip()

    # Call the GPU inference class
    generator = SQLGenerator()
    result    = generator.generate.remote(question, db_id)

    return result


# ── Local Testing ─────────────────────────────────────────────────────────────
@app.local_entrypoint()
def main():
    """
    Test the deployment locally before deploying.
    Run with: modal run deploy/modal_deploy.py
    """
    generator = SQLGenerator()

    test_cases = [
        ("How many singers do we have?",           "concert_singer"),
        ("Show all countries and number of singers","concert_singer"),
        ("What is the average age of all singers?", "concert_singer"),
    ]

    print("\n" + "=" * 60)
    print("  LOCAL TEST — Qwen SQL Generator")
    print("=" * 60)

    for question, db_id in test_cases:
        result = generator.generate.remote(question, db_id)
        print(f"\nQ  : {question}")
        print(f"DB : {db_id}")
        if result["success"]:
            print(f"SQL: {result['sql']}")
            print(f"⏱  : {result['latency_ms']}ms")
        else:
            print(f"ERR: {result['error']}")

    print("\n" + "=" * 60)
