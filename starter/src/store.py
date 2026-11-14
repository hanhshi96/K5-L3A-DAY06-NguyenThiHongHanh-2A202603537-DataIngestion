
"""PostgreSQL + pgvector storage and retrieval for Lab 06."""

from typing import Any
import math

import psycopg
from psycopg.types.json import Jsonb

from .models import Chunk


class PgVectorStore:
    ALLOWED_FILTERS = {
        "year",
        "company",
        "report_type",
        "language",
    }

    TABLE_NAME = "lab06_api_chunks"

    def __init__(self, database_url: str, dimensions: int) -> None:
        """Initialize PostgreSQL connection settings."""

        if not database_url:
            raise ValueError("DATABASE_URL is required")

        if dimensions <= 0:
            raise ValueError("dimensions must be positive")

        self.database_url = database_url
        self.dimensions = dimensions

    @staticmethod
    def _vector_literal(vector: list[float]) -> str:
        """Convert a validated vector to pgvector format."""

        values = []

        for value in vector:
            number = float(value)

            if not math.isfinite(number):
                raise ValueError("Vector contains non-finite values")

            values.append(str(number))

        return "[" + ",".join(values) + "]"

    def _validate_vector(self, vector: list[float]) -> None:
        if len(vector) != self.dimensions:
            raise ValueError(
                f"Expected {self.dimensions} dimensions, "
                f"received {len(vector)}"
            )

        self._vector_literal(vector)

    def create_schema(self) -> None:
        """Create pgvector table and metadata indexes."""

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:

                cur.execute(
                    "CREATE EXTENSION IF NOT EXISTS vector"
                )

                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
                        strategy TEXT NOT NULL,
                        chunk_id TEXT NOT NULL,
                        document_id TEXT NOT NULL,
                        source TEXT NOT NULL,
                        page INTEGER NOT NULL,
                        content TEXT NOT NULL,
                        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                        embedding vector({self.dimensions}) NOT NULL,
                        PRIMARY KEY (strategy, chunk_id)
                    )
                """)

                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS
                    idx_lab06_api_strategy_document
                    ON {self.TABLE_NAME} (strategy, document_id)
                """)

                cur.execute(f"""
                    CREATE INDEX IF NOT EXISTS
                    idx_lab06_api_strategy_year
                    ON {self.TABLE_NAME}
                    (strategy, (metadata ->> 'year'))
                """)

        print("PostgreSQL + pgvector schema ready.")

    def upsert(
        self,
        strategy: str,
        chunks: list[Chunk],
        vectors: list[list[float]],
    ) -> None:
        """Insert or update chunks without duplicates."""

        if not strategy:
            raise ValueError("strategy is required")

        if len(chunks) != len(vectors):
            raise ValueError(
                "Number of chunks and vectors must match"
            )

        if not chunks:
            print("No chunks to store.")
            return

        chunk_ids = [chunk.chunk_id for chunk in chunks]

        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("Duplicate chunk IDs detected")

        for chunk, vector in zip(chunks, vectors):
            if not chunk.document_id or not chunk.source:
                raise ValueError("Missing document metadata")

            if chunk.page < 1:
                raise ValueError("Page must be >= 1")

            if not chunk.text.strip():
                raise ValueError("Empty chunk detected")

            self._validate_vector(vector)

        # Group chunk IDs by document.
        document_chunks: dict[str, list[str]] = {}

        for chunk in chunks:
            document_chunks.setdefault(
                chunk.document_id, []
            ).append(chunk.chunk_id)

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:

                # Remove obsolete chunks from re-ingested documents.
                for document_id, current_ids in document_chunks.items():
                    cur.execute(
                        f"""
                        DELETE FROM {self.TABLE_NAME}
                        WHERE strategy = %s
                          AND document_id = %s
                          AND NOT (chunk_id = ANY(%s))
                        """,
                        (strategy, document_id, current_ids),
                    )

                # Insert or update current chunks.
                rows = []

                for chunk, vector in zip(chunks, vectors):
                    rows.append((
                        strategy,
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.source,
                        chunk.page,
                        chunk.text,
                        Jsonb(chunk.metadata),
                        self._vector_literal(vector),
                    ))

                cur.executemany(
                    f"""
                    INSERT INTO {self.TABLE_NAME} (
                        strategy,
                        chunk_id,
                        document_id,
                        source,
                        page,
                        content,
                        metadata,
                        embedding
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s::vector
                    )
                    ON CONFLICT (strategy, chunk_id)
                    DO UPDATE SET
                        document_id = EXCLUDED.document_id,
                        source = EXCLUDED.source,
                        page = EXCLUDED.page,
                        content = EXCLUDED.content,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding
                    """,
                    rows,
                )

        print(
            f"Stored {len(chunks)} chunks "
            f"for strategy {strategy}."
        )

    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Search using cosine similarity and optional metadata filters."""

        if not strategy:
            raise ValueError("strategy is required")

        if top_k <= 0:
            raise ValueError("top_k must be positive")

        self._validate_vector(query_vector)

        filters = filters or {}

        invalid_filters = set(filters) - self.ALLOWED_FILTERS

        if invalid_filters:
            raise ValueError(
                f"Unsupported filters: {invalid_filters}"
            )

        vector_text = self._vector_literal(query_vector)

        conditions = ["strategy = %s"]
        params: list[Any] = [strategy]

        # Parameterized metadata filtering.
        for key, value in filters.items():
            if value is None:
                raise ValueError(f"Filter {key} cannot be None")

            conditions.append("metadata ->> %s = %s")
            params.extend([key, str(value)])

        where_clause = " AND ".join(conditions)

        sql = f"""
            SELECT
                chunk_id,
                document_id,
                source,
                page,
                content,
                metadata,
                1 - (embedding <=> %s::vector) AS score
            FROM {self.TABLE_NAME}
            WHERE {where_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """

        query_params = [
            vector_text,
            *params,
            vector_text,
            top_k,
        ]

        with psycopg.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, query_params)
                rows = cur.fetchall()

        results = []

        for row in rows:
            results.append({
                "chunk_id": row[0],
                "document_id": row[1],
                "source": row[2],
                "page": row[3],
                "text": row[4],
                "metadata": row[5],
                "score": float(row[6]),
            })

        return results