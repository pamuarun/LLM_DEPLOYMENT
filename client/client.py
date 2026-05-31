"""
client.py
---------
HTTP client for the deployed Qwen SQL Generator API on Modal.

Usage:
    python client/client.py
"""

import os
import json
import requests
from typing import Optional

# ── Configuration ─────────────────────────────────────────────────────────────
# Replace with your actual Modal endpoint URL after deploying
ENDPOINT_URL = os.environ.get(
    "SQL_ENDPOINT_URL",
    "https://your-modal-endpoint-url.modal.run"
)
API_KEY = os.environ.get("SQL_API_KEY", "sk-sql-xxxxxxxxxxxxxxxxxxxx")


# ── Client Class ──────────────────────────────────────────────────────────────
class SQLGeneratorClient:
    """
    Client for interacting with the deployed Text-to-SQL API.
    """

    def __init__(self, endpoint_url: str, api_key: str):
        self.endpoint_url = endpoint_url
        self.api_key      = api_key
        self.session      = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
        })

    def generate_sql(
        self,
        question: str,
        db_id: str,
        timeout: int = 60,
    ) -> dict:
        """
        Send a natural language question and get a SQL query back.

        Args:
            question : Natural language question
            db_id    : Database identifier
            timeout  : Request timeout in seconds

        Returns:
            dict with keys: success, sql, question, db_id, latency_ms, error
        """
        payload = {
            "question" : question,
            "db_id"    : db_id,
            "api_key"  : self.api_key,
        }

        try:
            response = self.session.post(
                self.endpoint_url,
                json    = payload,
                timeout = timeout,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.Timeout:
            return {
                "success" : False,
                "sql"     : None,
                "error"   : "Request timed out — model may be cold starting (try again in 30s)",
                "question": question,
                "db_id"   : db_id,
            }
        except requests.exceptions.ConnectionError:
            return {
                "success" : False,
                "sql"     : None,
                "error"   : "Connection failed — check your endpoint URL",
                "question": question,
                "db_id"   : db_id,
            }
        except requests.exceptions.HTTPError as e:
            return {
                "success" : False,
                "sql"     : None,
                "error"   : f"HTTP error: {e.response.status_code} — {e.response.text}",
                "question": question,
                "db_id"   : db_id,
            }
        except Exception as e:
            return {
                "success" : False,
                "sql"     : None,
                "error"   : f"Unexpected error: {str(e)}",
                "question": question,
                "db_id"   : db_id,
            }

    def print_result(self, result: dict) -> None:
        """Pretty print a single result."""
        print(f"\n{'='*55}")
        print(f"  Question : {result['question']}")
        print(f"  Database : {result['db_id']}")
        print(f"{'='*55}")
        if result["success"]:
            print(f"  SQL      : {result['sql']}")
            print(f"  Latency  : {result.get('latency_ms', 'N/A')}ms")
        else:
            print(f"  ERROR    : {result['error']}")
        print(f"{'='*55}")


# ── Interactive Mode ──────────────────────────────────────────────────────────
def interactive_mode(client: SQLGeneratorClient) -> None:
    """Run an interactive session for generating SQL queries."""
    print("\n" + "="*55)
    print("  Qwen SQL Generator — Interactive Mode")
    print("  Type 'quit' to exit")
    print("="*55)

    while True:
        print()
        question = input("Enter your question: ").strip()
        if question.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break

        db_id = input("Enter database name : ").strip()
        if not db_id:
            db_id = "default_db"

        print("\nGenerating SQL...")
        result = client.generate_sql(question, db_id)
        client.print_result(result)


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    client = SQLGeneratorClient(ENDPOINT_URL, API_KEY)

    print("\nQwen SQL Generator Client")
    print(f"Endpoint : {ENDPOINT_URL}")
    print(f"API Key  : {API_KEY[:10]}...")

    # Quick health check
    print("\nRunning health check...")
    result = client.generate_sql(
        question = "How many records are there?",
        db_id    = "test_db",
    )

    if result["success"]:
        print("✅ API is online and responding!")
        client.print_result(result)
    else:
        print(f"⚠️  API returned error: {result['error']}")

    # Launch interactive mode
    interactive_mode(client)
