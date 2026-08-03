"""Grounded-answer prompt construction.

The system prompt is the primary hallucination control. It:
  1. Forbids using any knowledge outside the provided context.
  2. Requires an inline [n] citation for every claim.
  3. Mandates an explicit refusal phrase when evidence is insufficient.

Each context block is labelled with a stable [n] marker plus its source
(filename + page/section) so the model can cite precisely and we can map the
markers back to structured Citation objects.
"""
from __future__ import annotations

from typing import List, Tuple

REFUSAL_PHRASE = "The provided documents do not contain enough information to answer this question."

SYSTEM_PROMPT = f"""You are a meticulous knowledge assistant that answers strictly from a set of retrieved document excerpts.

Rules — follow them exactly:
1. Use ONLY the information in the CONTEXT blocks below. Never use prior knowledge, assumptions, or outside facts.
2. Support every factual statement with an inline citation using the block's marker, e.g. "Revenue grew 12% [2]." Cite every block you rely on.
3. If the context does not contain enough information to answer, respond with EXACTLY this sentence and nothing else:
   "{REFUSAL_PHRASE}"
4. Do not speculate, do not fill gaps, and never invent citations. A partial answer with a clear statement of what is missing is better than a fabricated one.
5. Be concise and factual. Quote figures and names exactly as they appear in the context.
"""


def build_context_block(chunks: List[dict]) -> Tuple[str, List[dict]]:
    """Return (context_text, ordered_chunks). ordered_chunks[i] corresponds to marker i+1."""
    lines: List[str] = []
    for i, ch in enumerate(chunks, start=1):
        src = ch.get("filename", "unknown")
        loc = []
        if ch.get("page") is not None:
            loc.append(f"page {ch['page']}")
        if ch.get("section"):
            loc.append(f"section “{ch['section']}”")
        loc_str = f" ({', '.join(loc)})" if loc else ""
        lines.append(f"[{i}] Source: {src}{loc_str}\n{ch['text'].strip()}")
    return "\n\n".join(lines), chunks


def build_user_prompt(question: str, context_text: str) -> str:
    if not context_text.strip():
        context_text = "(no relevant excerpts were retrieved)"
    return (
        f"CONTEXT:\n{context_text}\n\n"
        f"QUESTION: {question}\n\n"
        "Answer using only the context above, with inline [n] citations."
    )
