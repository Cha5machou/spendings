"""Copy a local Spendings database (SQLite) into PostgreSQL, and optionally its documents into a
Cloud Storage bucket. Run it yourself, once, from the backend folder:

    uv run python scripts/migrate_to_cloud.py \
        --target "postgresql+psycopg2://USER:PASSWORD@127.0.0.1:5432/DB" \
        --bucket my-spendings-documents

Use the Cloud SQL Auth Proxy (see docs/DEPLOY_GCP.md) to reach Cloud SQL from your computer.
The target must be empty unless you pass --force (which empties it first)."""

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlmodel import SQLModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.models  # noqa: E402,F401  (registers every table)
from app.config import settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=f"sqlite:///{settings.data_dir / 'spendings.db'}")
    parser.add_argument("--target", required=True, help="PostgreSQL SQLAlchemy URL")
    parser.add_argument("--documents-dir", default=str(settings.documents_dir))
    parser.add_argument("--bucket", help="Cloud Storage bucket for the uploaded statements (skip to leave documents behind)")
    parser.add_argument("--force", action="store_true", help="empty the target tables first")
    arguments = parser.parse_args()

    source = create_engine(arguments.source)
    target = create_engine(arguments.target)
    tables = SQLModel.metadata.sorted_tables

    with target.begin() as connection:
        if arguments.force:
            for table in reversed(tables):
                connection.execute(text(f'DROP TABLE IF EXISTS "{table.name}" CASCADE'))
    SQLModel.metadata.create_all(target)

    with target.connect() as connection:
        occupied = [table.name for table in tables if connection.execute(table.select().limit(1)).first() is not None]
    if occupied:
        sys.exit(f"The target already holds data in: {', '.join(occupied)}. Use --force to replace it.")

    with source.connect() as reading, target.begin() as writing:
        for table in tables:
            rows = [dict(row._mapping) for row in reading.execute(table.select())]
            for start in range(0, len(rows), 500):
                writing.execute(table.insert(), rows[start:start + 500])
            print(f"{table.name:24} {len(rows):6} rows")
        # Keep auto-increment ids going after the copied maximum.
        for table in tables:
            if "id" in table.c and table.c.id.primary_key:
                writing.execute(text(
                    f"""SELECT setval(pg_get_serial_sequence('"{table.name}"', 'id'), COALESCE((SELECT MAX(id) FROM "{table.name}"), 1))
                        WHERE pg_get_serial_sequence('"{table.name}"', 'id') IS NOT NULL"""))

    if arguments.bucket:
        from google.cloud import storage

        bucket = storage.Client().bucket(arguments.bucket)
        document_table = SQLModel.metadata.tables["document"]
        folder = Path(arguments.documents_dir)
        uploaded = 0
        with target.begin() as connection:
            for document in connection.execute(document_table.select()).mappings():
                local = folder / document["stored_path"]
                if not local.is_file():
                    print(f"  missing file for document {document['id']}: {document['stored_path']}")
                    continue
                name = f"documents/{document['stored_path']}"
                bucket.blob(name).upload_from_filename(str(local))
                connection.execute(document_table.update().where(document_table.c.id == document["id"]).values(stored_path=name))
                uploaded += 1
        print(f"uploaded {uploaded} documents to gs://{arguments.bucket}/documents/")
    print("done")


if __name__ == "__main__":
    main()
