"""OpenAI embeddings via Python's standard library."""

import json
import math
import os
import time
import urllib.error
import urllib.request


class MyEmbedder:
    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
    ) -> None:
        self.model_name = model_name
        self.dimensions = 1536

        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError("Missing OPENAI_API_KEY in .env")

        self.total_tokens = 0

    def embed_documents(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        if not texts:
            return []

        for text in texts:
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Embedding input must be non-empty text.")

            if len(text.encode("utf-8")) > 6000:
                raise ValueError(
                    "Text is too large for this pipeline. Split it first."
                )

        vectors = []

        for start in range(0, len(texts), 32):
            batch = texts[start:start + 32]

            print(
                f"Embedding {start + 1}–{start + len(batch)}/{len(texts)}",
                flush=True,
            )

            vectors.extend(self._request(batch))

        return vectors

    def _request(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps({
            "model": self.model_name,
            "input": texts,
            "dimensions": self.dimensions,
            "encoding_format": "float",
        }).encode("utf-8")

        request = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        for attempt in range(3):
            try:
                with urllib.request.urlopen(
                    request,
                    timeout=60,
                ) as response:
                    payload = json.load(response)

                rows = sorted(
                    payload["data"],
                    key=lambda item: item["index"],
                )

                if [row["index"] for row in rows] != list(range(len(texts))):
                    raise RuntimeError("Unexpected embedding response indices.")

                vectors = [row["embedding"] for row in rows]

                for vector in vectors:
                    if (
                        len(vector) != self.dimensions
                        or not all(math.isfinite(x) for x in vector)
                        or not any(x != 0 for x in vector)
                    ):
                        raise RuntimeError("Invalid embedding vector.")

                self.total_tokens += payload.get(
                    "usage", {}
                ).get("total_tokens", 0)

                return vectors

            except urllib.error.HTTPError as error:
                raw = error.read().decode("utf-8", errors="replace")

                try:
                    code = json.loads(raw).get("error", {}).get("code")
                except ValueError:
                    code = None

                retryable = (
                    error.code in {429, 500, 502, 503, 504}
                    and code != "insufficient_quota"
                )

                if retryable and attempt < 2:
                    print(
                        f"API HTTP {error.code}; retrying...",
                        flush=True,
                    )
                    time.sleep(2 ** (attempt + 1))
                    continue

                raise RuntimeError(
                    f"OpenAI HTTP {error.code}; code={code}. "
                    "Check API key, credit, and model access."
                ) from None

            except (urllib.error.URLError, TimeoutError):
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                    continue

                raise RuntimeError(
                    "Cannot connect to OpenAI. "
                    "Check network and HTTPS certificates."
                ) from None

        raise RuntimeError("Embedding request failed.")

    def embed_query(self, question: str) -> list[float]:
        return self.embed_documents([question])[0]