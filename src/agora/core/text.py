"""Découpage de texte : fonctions pures, partagées par les ingestions et les serveurs MCP."""

CHUNK_OVERLAP = 200


def chunk_text(text: str, max_chars: int = 1500, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Découpe sur les paragraphes puis, si besoin, en fenêtres glissantes."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    chunks, current = [], ""
    for para in (p.strip() for p in text.split("\n") if p.strip()):
        if len(current) + len(para) + 1 <= max_chars:
            current = f"{current}\n{para}" if current else para
            continue
        if current:
            chunks.append(current)
        while len(para) > max_chars:
            chunks.append(para[:max_chars])
            para = para[max_chars - overlap :]
        current = para
    if current:
        chunks.append(current)
    return chunks


def join_chunks(chunks: list[str], overlap: int = CHUNK_OVERLAP) -> str:
    """Inverse de chunk_text : recolle les chunks sans dupliquer le recouvrement des fenêtres glissantes."""
    if not chunks:
        return ""
    out = chunks[0]
    for prev, cur in zip(chunks, chunks[1:], strict=False):
        if len(prev) >= overlap and cur[:overlap] == prev[-overlap:]:
            out += cur[overlap:]  # fenêtre glissante : suite directe du même paragraphe
        else:
            out += "\n" + cur
    return out
