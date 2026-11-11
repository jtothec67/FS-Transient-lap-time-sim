"""Write a DeepSeek API key to config/deepseek_key for the chat service."""
import sys
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
KEY_PATH = CONFIG_DIR / "deepseek_key"


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python tools/encrypt_api_key.py <deepseek-api-key>")
        sys.exit(1)
    CONFIG_DIR.mkdir(exist_ok=True)
    KEY_PATH.write_text(sys.argv[1].strip(), encoding="utf-8")
    print(f"Saved to {KEY_PATH}")


if __name__ == "__main__":
    main()
