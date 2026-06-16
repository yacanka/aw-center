from sentence_transformers import SentenceTransformer, CrossEncoder
from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from typing import List, Dict, Any, Optional, Literal, IO
import numpy as np
import os
import re


# =========================================================
# CONSTANTS
# =========================================================
# Nihai karar için sabit eşikler
FINAL_STRONG_THRESHOLD = 0.78
FINAL_PARTIAL_THRESHOLD = 0.58

# İlk aşama retrieval ayarları
DEFAULT_CHUNK_CHAR_LIMIT = 900
DEFAULT_SENTENCE_GROUP_SIZE = 3
DEFAULT_SENTENCE_OVERLAP = 1
FIRST_STAGE_TOP_K = 20
SECOND_STAGE_TOP_K = 8

# Skor birleştirme
BI_ENCODER_WEIGHT = 0.40
CROSS_ENCODER_WEIGHT = 0.50
LEXICAL_WEIGHT = 0.10

# Başlık etkisi
DEFAULT_HEADING_BOOST = 1.08

ContentMode = Literal["paragraph", "table", "both"]


class ExplainableDocxRetriever:
    def __init__(
        self,
        model_path: str,
        cross_encoder_model: str,
        backend: Optional[str] = None,
        content_mode: ContentMode = "both",
        use_heading_weight: bool = True,
        heading_boost: float = DEFAULT_HEADING_BOOST,
    ):
        """
        model_path:
            Bi-encoder sentence-transformers model klasörü

        cross_encoder_model:
            Cross-encoder model adı ya da lokal klasörü
            Örn:
            - "cross-encoder/ms-marco-MiniLM-L-6-v2"
            - lokal klasör yolu

        backend:
            None / "onnx" / "openvino"

        content_mode:
            "paragraph" / "table" / "both"
        """
        if backend is None:
            self.bi_encoder = SentenceTransformer(model_path)
        else:
            self.bi_encoder = SentenceTransformer(model_path, backend=backend)

        self.cross_encoder = CrossEncoder(cross_encoder_model)

        self.content_mode = content_mode
        self.use_heading_weight = use_heading_weight
        self.heading_boost = heading_boost

        self.units: List[Dict[str, Any]] = []
        self.unit_embeddings: Optional[np.ndarray] = None

        self.stopwords = {
            "ve", "veya", "ile", "için", "gibi", "olan", "olarak", "bir", "bu", "şu",
            "da", "de", "mi", "mı", "mu", "mü", "var", "yok", "ilgili", "ait", "the",
            "is", "are", "of", "to", "in", "on", "for", "a", "an", "and", "or"
        }

    # =========================================================
    # TEXT HELPERS
    # =========================================================
    def _normalize_text(self, text: str) -> str:
        return " ".join(text.strip().split())

    def _is_heading(self, paragraph) -> bool:
        try:
            style_name = paragraph.style.name if paragraph.style else ""
        except Exception:
            style_name = ""
        s = style_name.lower() if style_name else ""
        return ("heading" in s) or ("başlık" in s)

    def _tokenize_for_lexical(self, text: str) -> List[str]:
        text = text.lower()
        text = re.sub(r"[^\wçğıöşüİÇĞIÖŞÜ\s]", " ", text, flags=re.UNICODE)
        return [t for t in text.split() if t and t not in self.stopwords and len(t) > 1]

    def _lexical_overlap_score(self, query: str, text: str) -> float:
        q_tokens = set(self._tokenize_for_lexical(query))
        t_tokens = set(self._tokenize_for_lexical(text))
        if not q_tokens or not t_tokens:
            return 0.0
        inter = len(q_tokens & t_tokens)
        return min(inter / max(len(q_tokens), 1), 1.0)

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Basit ama pratik cümle bölücü.
        """
        text = self._normalize_text(text)
        if not text:
            return []

        # Nokta, soru, ünlem, satır sonu temelli kaba bölme
        parts = re.split(r'(?<=[\.\?\!])\s+|\n+', text)
        sentences = [self._normalize_text(p) for p in parts if self._normalize_text(p)]
        return sentences

    def _sentence_chunk(
        self,
        text: str,
        sentence_group_size: int = DEFAULT_SENTENCE_GROUP_SIZE,
        sentence_overlap: int = DEFAULT_SENTENCE_OVERLAP,
        char_limit: int = DEFAULT_CHUNK_CHAR_LIMIT
    ) -> List[str]:
        """
        Cümle bazlı chunking:
        - metni cümlelere böler
        - birkaç cümleyi birleştirir
        - overlap uygular
        - çok uzun chunk oluşursa karakter sınırına göre böler
        """
        sentences = self._split_into_sentences(text)
        if not sentences:
            return []

        if sentence_group_size <= sentence_overlap:
            raise ValueError("sentence_group_size, sentence_overlap'tan büyük olmalı")

        chunks = []
        step = sentence_group_size - sentence_overlap

        i = 0
        while i < len(sentences):
            group = sentences[i:i + sentence_group_size]
            if not group:
                break

            chunk = " ".join(group).strip()

            if len(chunk) <= char_limit:
                chunks.append(chunk)
            else:
                # fallback: uzun grupsa karakter bazlı alt bölme
                start = 0
                while start < len(chunk):
                    piece = chunk[start:start + char_limit].strip()
                    if piece:
                        chunks.append(piece)
                    start += max(char_limit - 120, 1)

            i += step

        return chunks

    def _table_to_row_texts(self, table) -> List[Dict[str, Any]]:
        """
        İlk dolu satırı header varsayar.
        Sonraki satırları:
        'kolon: değer' biçiminde zenginleştirir.
        """
        raw_rows = []
        for row in table.rows:
            cells = [self._normalize_text(cell.text) for cell in row.cells]
            if any(cells):
                raw_rows.append(cells)

        if not raw_rows:
            return []

        header = raw_rows[0]
        has_header = any(header)

        rows = []
        for r_idx, row in enumerate(raw_rows):
            plain_parts = []
            mapped_parts = []

            for c_idx, cell_val in enumerate(row):
                if not cell_val:
                    continue
                plain_parts.append(cell_val)

                if has_header and r_idx > 0 and c_idx < len(header) and header[c_idx]:
                    mapped_parts.append(f"{header[c_idx]}: {cell_val}")

            plain_text = " | ".join(plain_parts).strip()
            mapped_text = " ; ".join(mapped_parts).strip()
            combined = plain_text if not mapped_text else f"{plain_text} || {mapped_text}"

            rows.append({
                "row_index": r_idx,
                "is_header_row": r_idx == 0,
                "header_text": " | ".join(header).strip() if has_header else None,
                "text": combined
            })

        return rows

    # =========================================================
    # ENCODING HELPERS
    # =========================================================
    def _encode_documents(self, texts: List[str], show_progress_bar: bool = False) -> np.ndarray:
        if hasattr(self.bi_encoder, "encode_document"):
            return self.bi_encoder.encode_document(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=show_progress_bar
            )
        return self.bi_encoder.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=show_progress_bar
        )

    def _encode_query(self, query: str) -> np.ndarray:
        if hasattr(self.bi_encoder, "encode_query"):
            return self.bi_encoder.encode_query(
                query,
                convert_to_numpy=True,
                normalize_embeddings=True
            )
        return self.bi_encoder.encode(
            query,
            convert_to_numpy=True,
            normalize_embeddings=True
        )

    # =========================================================
    # DOCX INGESTION
    # =========================================================
    def _iter_block_items(self, doc):
        """
        DOCX içindeki paragraph ve table elemanlarını gerçek sırayla döndürür.
        """
        for child in doc.element.body.iterchildren():
            if isinstance(child, CT_P):
                yield Paragraph(child, doc)
            elif isinstance(child, CT_Tbl):
                yield Table(child, doc)
    
    def add_docx_file(
        self,
        file: str | IO[bytes],
        file_name: str | None = None,
        sentence_group_size: int = DEFAULT_SENTENCE_GROUP_SIZE,
        sentence_overlap: int = DEFAULT_SENTENCE_OVERLAP,
        char_limit: int = DEFAULT_CHUNK_CHAR_LIMIT
) ->     None:

        if isinstance(file, str):
            doc = Document(file)
            resolved_file_name = os.path.basename(file)
            file_path = file
        else:
            file.seek(0)
            doc = Document(file)
            resolved_file_name = file_name or getattr(file, "name", "uploaded.docx")
            resolved_file_name = os.path.basename(resolved_file_name)
            file_path = resolved_file_name

        current_heading = None
        paragraph_index = 0
        table_index = 0

        for block in self._iter_block_items(doc):

            if isinstance(block, Paragraph):
                text = self._normalize_text(block.text)
                if not text:
                    continue

                if self._is_heading(block):
                    current_heading = text

                    if self.content_mode in ("paragraph", "both"):
                        self.units.append({
                            "text": text,
                            "source_type": "heading",
                            "heading": current_heading,
                            "file_path": file_path,
                            "file_name": resolved_file_name,
                            "paragraph_index": paragraph_index,
                        })

                    paragraph_index += 1
                    continue

                if self.content_mode in ("paragraph", "both"):
                    chunks = self._sentence_chunk(
                        text,
                        sentence_group_size=sentence_group_size,
                        sentence_overlap=sentence_overlap,
                        char_limit=char_limit
                    )

                    for c_idx, chunk in enumerate(chunks):
                        self.units.append({
                            "text": chunk,
                            "source_type": "paragraph",
                            "heading": current_heading,
                            "file_path": file_path,
                            "file_name": resolved_file_name,
                            "paragraph_index": paragraph_index,
                            "chunk_index": c_idx,
                        })

                paragraph_index += 1

            elif isinstance(block, Table):
                if self.content_mode in ("table", "both"):
                    row_infos = self._table_to_row_texts(block)

                    for row_info in row_infos:
                        chunks = self._sentence_chunk(
                            row_info["text"],
                            sentence_group_size=sentence_group_size,
                            sentence_overlap=sentence_overlap,
                            char_limit=char_limit
                        )

                        for c_idx, chunk in enumerate(chunks):
                            self.units.append({
                                "text": chunk,
                                "source_type": "table",
                                "heading": current_heading,
                                "file_path": file_path,
                                "file_name": resolved_file_name,
                                "table_index": table_index,
                                "row_index": row_info["row_index"],
                                "chunk_index": c_idx,
                                "is_header_row": row_info["is_header_row"],
                                "table_header_text": row_info["header_text"],
                            })

                table_index += 1

    def add_docx_folder(
        self,
        folder_path: str,
        sentence_group_size: int = DEFAULT_SENTENCE_GROUP_SIZE,
        sentence_overlap: int = DEFAULT_SENTENCE_OVERLAP,
        char_limit: int = DEFAULT_CHUNK_CHAR_LIMIT
    ) -> None:
        for file_name in os.listdir(folder_path):
            if file_name.lower().endswith(".docx"):
                self.add_docx_file(
                    os.path.join(folder_path, file_name),
                    sentence_group_size=sentence_group_size,
                    sentence_overlap=sentence_overlap,
                    char_limit=char_limit
                )

    def build_index(self) -> None:
        if not self.units:
            raise ValueError("Önce belge eklemelisin")

        texts = [u["text"] for u in self.units]
        self.unit_embeddings = self._encode_documents(texts, show_progress_bar=False)

    # =========================================================
    # SCORING
    # =========================================================
    def _apply_heading_weight(self, score: float, unit: Dict[str, Any]) -> float:
        if not self.use_heading_weight:
            return min(score, 1.0)

        if unit["source_type"] == "heading":
            score *= self.heading_boost
        elif unit.get("heading"):
            score *= self.heading_boost

        return min(score, 1.0)

    def _bi_stage_search(self, query: str, top_k: int = FIRST_STAGE_TOP_K) -> List[Dict[str, Any]]:
        if self.unit_embeddings is None:
            raise ValueError("Önce build_index() çağırmalısın")

        query_emb = self._encode_query(query)
        scores = np.dot(self.unit_embeddings, query_emb)
        order = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in order:
            unit = self.units[idx]
            lexical = self._lexical_overlap_score(query, unit["text"])

            blended = (
                float(scores[idx]) * 0.88 +
                lexical * 0.12
            )
            blended = self._apply_heading_weight(blended, unit)

            results.append({
                "unit_id": int(idx),
                "text": unit["text"],
                "metadata": unit,
                "bi_score": float(scores[idx]),
                "lexical_score": float(lexical),
                "first_stage_score": float(blended)
            })

        results.sort(key=lambda x: x["first_stage_score"], reverse=True)
        return results

    def _rerank_with_cross_encoder(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = SECOND_STAGE_TOP_K
    ) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        pairs = [(query, c["text"]) for c in candidates]
        ce_scores = self.cross_encoder.predict(pairs)

        reranked = []
        for cand, ce_score in zip(candidates, ce_scores):
            ce_score = float(ce_score)

            # Bazı cross-encoder modelleri 0-1, bazıları daha geniş aralık verebilir.
            # Güvenli normalize yaklaşımı:
            if ce_score < 0.0:
                ce_norm = 1 / (1 + np.exp(-ce_score))  # sigmoid
            elif ce_score > 1.0:
                ce_norm = 1 / (1 + np.exp(-ce_score))  # sigmoid
            else:
                ce_norm = ce_score

            final = (
                cand["bi_score"] * BI_ENCODER_WEIGHT +
                ce_norm * CROSS_ENCODER_WEIGHT +
                cand["lexical_score"] * LEXICAL_WEIGHT
            )
            final = self._apply_heading_weight(final, cand["metadata"])

            item = dict(cand)
            item["cross_score_raw"] = ce_score
            item["cross_score_norm"] = float(ce_norm)
            item["final_score"] = float(min(final, 1.0))
            reranked.append(item)

        reranked.sort(key=lambda x: x["final_score"], reverse=True)
        return reranked[:top_k]

    # =========================================================
    # EXPLANATION
    # =========================================================
    def _build_explanation_text(
        self,
        query: str,
        reranked: List[Dict[str, Any]]
    ) -> str:
        if not reranked:
            return (
                f'"{query}" ifadesini açıkça doğrulayan güçlü bir eşleşme bulunamadı. '
                f'İlgili başlık, paragraf veya tablo satırı yeterli benzerlik göstermedi.'
            )

        best = reranked[0]
        best_score = best["final_score"]

        if best_score >= FINAL_STRONG_THRESHOLD:
            strength = "güçlü"
            conclusion = "Dokümanda bu maddeyi destekleyen güçlü kanıt bulundu."
        elif best_score >= FINAL_PARTIAL_THRESHOLD:
            strength = "orta"
            conclusion = "Dokümanda bu maddeyi kısmen destekleyen kanıt bulundu, ancak ifade tam ve doğrudan olmayabilir."
        else:
            strength = "zayıf"
            conclusion = "Dokümanda bu maddeye dair yalnızca zayıf veya dolaylı benzerlik bulundu."

        evidence_lines = []
        for i, item in enumerate(reranked[:3], start=1):
            md = item["metadata"]
            source = md.get("source_type", "unknown")
            heading = md.get("heading")
            file_name = md.get("file_name", "")
            text_snippet = item["text"][:220].strip()

            location = f"dosya={file_name}, kaynak={source}"
            if heading:
                location += f', başlık="{heading}"'

            evidence_lines.append(
                f"{i}. Kanıt ({location}) | nihai skor={item['final_score']:.3f} | metin: {text_snippet}"
            )

        explanation = (
            f"{conclusion} "
            f"En güçlü eşleşme {strength} seviyede bulundu "
            f"(nihai skor={best_score:.3f}, bi-encoder={best['bi_score']:.3f}, "
            f"cross-encoder={best['cross_score_norm']:.3f}, lexical={best['lexical_score']:.3f}). "
            f"En ilgili kanıtlar: " + " ".join(evidence_lines)
        )
        return explanation

    # =========================================================
    # PUBLIC SEARCH
    # =========================================================
    def search(self, query: str) -> Dict[str, Any]:
        first_stage = self._bi_stage_search(query, top_k=FIRST_STAGE_TOP_K)
        second_stage = self._rerank_with_cross_encoder(query, first_stage, top_k=SECOND_STAGE_TOP_K)

        best_score = second_stage[0]["final_score"] if second_stage else 0.0

        explanation = self._build_explanation_text(query, second_stage)

        return {
            "query": query,
            "best_score": float(best_score),
            "results": second_stage,
            "explanation": explanation
        }


if __name__ == "__main__":
    MODEL_PATH = r"C:\Users\t02077\Desktop\Code\Models\paraphrase-multilingual-MiniLM-L12-v2"  # bi-encoder klasörü
    CROSS_ENCODER_MODEL = r"C:\Users\t02077\Desktop\Code\Models\ms-marco-MiniLM-L6-v2"
    DOCX_FOLDER = r"C:\Users\t02077\Desktop\Code\Test\Hugging Face"

    engine = ExplainableDocxRetriever(
        model_path=MODEL_PATH,
        cross_encoder_model=CROSS_ENCODER_MODEL,
        #backend="openvino",   # None / "onnx" / "openvino"
        content_mode="both",
        use_heading_weight=True
    )

    engine.add_docx_folder(
        DOCX_FOLDER,
        sentence_group_size=3,
        sentence_overlap=1,
        char_limit=900
    )

    engine.build_index()

    queries = [
        "Do you have a list of compliance documents?",
        "Who is the author?",
        "Is there an attachments section?"
    ]

    for q in queries:
        result = engine.search(q)
        print("=" * 120)
        print("QUERY      :", result["query"])
        print("BEST SCORE :", f"{result['best_score']:.4f}")
        print("EXPLANATION:")
        print(result["explanation"])
        print("-" * 120)

        for i, item in enumerate(result["results"], start=1):
            md = item["metadata"]
            print(
                f"[{i}] final={item['final_score']:.4f} "
                f"bi={item['bi_score']:.4f} "
                f"cross={item['cross_score_norm']:.4f} "
                f"lexical={item['lexical_score']:.4f}"
            )
            print("file       :", md.get("file_name"))
            print("source_type:", md.get("source_type"))
            print("heading    :", md.get("heading"))
            print("text       :", item["text"][:300])
            print("-" * 120)