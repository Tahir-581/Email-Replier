import pathlib

from sqlalchemy import create_engine, text


def load_dotenv(path: pathlib.Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        data[k.strip()] = v.strip()
    return data


def main() -> None:
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    dotenv_path = repo_root / ".env"
    if not dotenv_path.exists():
        raise SystemExit(f"Missing .env at: {dotenv_path}")

    env = load_dotenv(dotenv_path)
    database_url = env.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL not found in .env")

    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto;"))

    print("pgcrypto ensured")


if __name__ == "__main__":
    main()

