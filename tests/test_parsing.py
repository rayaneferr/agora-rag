from pathlib import Path

from agora.common import chunk_text, join_chunks
from agora.ingestion.assemblee import parse_seance, to_chunks

SEANCE = (Path(__file__).parent / "fixtures" / "seance.xml").read_bytes()


def interventions():
    return list(parse_seance(SEANCE))


def test_decoupe_par_intervention():
    orateurs = [i["orateur"] for i in interventions()]
    assert orateurs == ["Mme Alice Martin", "Mme Claire Dubois", "M. Bruno Petit"]


def test_exclut_presidence_et_didascalies():
    textes = " ".join(i["text"] for i in interventions())
    assert "La parole est à" not in textes
    assert "Applaudissements" not in textes


def test_interjection_ne_coupe_pas_l_intervention():
    ministre = next(i for i in interventions() if i["orateur"] == "Mme Claire Dubois")
    assert "priorité absolue" in ministre["text"]
    assert "vérification de l’âge" in ministre["text"]
    assert "Très bien" not in ministre["text"]


def test_metadonnees():
    first = interventions()[0]
    assert first["date"] == "2024-11-06"
    assert first["date_int"] == 20241106
    assert first["section"] == "Questions au Gouvernement"
    assert first["sujet"] == "Régulation des réseaux sociaux"
    assert first["ordre"] == 9
    assert first["url"].endswith("/CRSANR5L17S2025O1N999")


def test_br_ne_colle_pas_les_phrases():
    first = interventions()[0]
    assert "âge. Quelles" in first["text"] or "âge.\nQuelles" in first["text"]


def test_qualite_ministre():
    ministre = next(i for i in interventions() if i["orateur"] == "Mme Claire Dubois")
    assert ministre["qualite"] == "ministre du numérique"


def test_chunk_prefixe_orateur_et_sujet():
    text, payload = to_chunks(interventions()[0])[0]
    assert text.startswith("Mme Alice Martin (2024-11-06) — Régulation des réseaux sociaux\n")
    assert payload["chunk_index"] == 0
    assert "Mme Alice Martin" not in payload["text"]


def test_chunk_text_court():
    assert chunk_text("  bonjour  ") == ["bonjour"]


def test_chunk_text_respecte_la_taille():
    text = "\n".join(f"Paragraphe {i} " + "x" * 400 for i in range(10))
    chunks = chunk_text(text, max_chars=1000)
    assert len(chunks) > 1
    assert all(len(c) <= 1000 for c in chunks)
    assert "Paragraphe 0" in chunks[0] and "Paragraphe 9" in chunks[-1]


def test_chunk_text_paragraphe_geant_avec_recouvrement():
    chunks = chunk_text("a" * 2500, max_chars=1000, overlap=200)
    assert all(len(c) <= 1000 for c in chunks)
    assert sum(len(c) for c in chunks) >= 2500


def test_join_chunks_inverse_chunk_text():
    text = "Intro.\n" + "b" * 3000 + "\nConclusion."
    assert join_chunks(chunk_text(text, max_chars=1000)) == text
