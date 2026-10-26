"""Create a local .env with independent random signing keys."""
from pathlib import Path
import secrets


def main():
    root = Path(__file__).resolve().parents[1]
    target = root / ".env"
    if target.exists():
        raise SystemExit(".env already exists; existing settings were preserved")
    content = (root / ".env.example").read_text()
    content = content.replace("SESSION_SECRET=\n", f"SESSION_SECRET={secrets.token_hex(32)}\n")
    content = content.replace("JWT_SECRET=\n", f"JWT_SECRET={secrets.token_hex(32)}\n")
    with target.open("x") as stream:
        target.chmod(0o600)
        stream.write(content)
    print("Created .env with random SESSION_SECRET and JWT_SECRET")


if __name__ == "__main__":
    main()
