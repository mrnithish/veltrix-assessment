"""Download the embedding model and the tiktoken encoding at image build time,
so the running service needs no network access except the LLM API."""

import os

import tiktoken
from fastembed import TextEmbedding

tiktoken.get_encoding("cl100k_base").encode("warm up")
model = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
list(TextEmbedding(model_name=model, cache_dir=os.environ.get("FASTEMBED_CACHE_PATH")).embed(["warm up"]))
print(f"prefetched cl100k_base and {model}")

# OCR: RapidOCR ships its ONNX models in the wheel; one warm-up run verifies they load in this image.
import numpy as np  # noqa: E402
from rapidocr import RapidOCR  # noqa: E402

RapidOCR()(np.full((64, 256, 3), 255, dtype=np.uint8))
print("prefetched RapidOCR models")
