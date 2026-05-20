import math
import os
import re
from dataclasses import dataclass, field
from collections import defaultdict, OrderedDict, Counter
from typing import Any, Optional

import fitz
from unstructured.partition.auto import partition

from module.node.base.base import BaseProcessor


# =========================================================
# 기본 설정
# =========================================================

STOPWORDS = {
    "the", "is", "a", "an", "of", "to", "and", "or", "in", "on", "for", "with",
    "what", "how", "why", "when", "where", "which", "who", "whom",
    "does", "do", "did", "can", "could", "would", "should", "may", "might",
    "it", "this", "that", "these", "those", "are", "was", "were", "be", "been",
    "as", "at", "by", "from", "into", "about", "through"
}

TEXT_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".py", ".java", ".c", ".cpp", ".h", ".hpp",
    ".json", ".yaml", ".yml", ".ini", ".cfg", ".log", ".csv", ".tsv", ".html", ".htm"
}


# =========================================================
# 문자열 처리
# =========================================================

def simple_stem(word: str) -> str:
    w = word.lower()

    if len(w) <= 3:
        return w

    suffixes = [
        "ization", "ational", "fulness", "ousness", "iveness", "tional",
        "biliti", "lessli", "entli", "ation", "alism", "aliti", "iviti",
        "ousli", "enci", "anci", "izer", "ator", "alli", "bli", "ogi", "li",
        "ing", "edly", "edly", "ed", "ly", "es", "s"
    ]

    for suf in suffixes:
        if w.endswith(suf) and len(w) > len(suf) + 2:
            w = w[:-len(suf)]
            break

    if len(w) >= 2 and w[-1] == w[-2]:
        w = w[:-1]

    return w


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def tokenize_raw(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_]+(?:[-_][a-zA-Z0-9_]+)?", text.lower())


def normalize_term(term: str) -> str:
    term = term.lower().replace("-", "_")
    parts = [simple_stem(p) for p in term.split("_") if p]
    return "_".join(parts)


def split_compound(term: str) -> list[str]:
    term = term.lower().replace("-", "_")
    parts = [p for p in term.split("_") if p]
    return [normalize_term(p) for p in parts if p]


def build_base_terms(text: str) -> list[str]:
    """
    문서/질의 공통 토큰 정규화:
    - unigram
    - 복합어면 compound 전체 + 분해 토큰
    """
    out = []

    for raw in tokenize_raw(text):
        norm = normalize_term(raw)

        if len(norm.replace("_", "")) >= 2 and norm not in STOPWORDS:
            out.append(norm)

        if "_" in raw:
            for part in split_compound(raw):
                if len(part) >= 2 and part not in STOPWORDS:
                    out.append(part)

    return out


def make_ngrams(terms: list[str], n: int) -> list[str]:
    if len(terms) < n:
        return []
    return ["__".join(terms[i:i+n]) for i in range(len(terms) - n + 1)]


def build_query_terms(query: str) -> tuple[list[str], list[str], list[str]]:
    """
    반환:
    - unigrams
    - bigrams
    - trigrams
    """
    base = build_base_terms(query)

    # stopword 제거가 base에서 이미 대부분 반영되지만 재한번 정리
    uni = [t for t in base if t not in STOPWORDS and len(t) >= 2]
    bi = make_ngrams(uni, 2)
    tri = make_ngrams(uni, 3)

    return uni, bi, tri


# =========================================================
# LRU 캐시
# =========================================================

class LRUCache:
    def __init__(self, capacity: int = 128):
        self.capacity = max(1, capacity)
        self._data = OrderedDict()

    def get(self, key):
        if key not in self._data:
            return None
        value = self._data.pop(key)
        self._data[key] = value
        return value

    def set(self, key, value):
        if key in self._data:
            self._data.pop(key)
        elif len(self._data) >= self.capacity:
            self._data.popitem(last=False)
        self._data[key] = value


# =========================================================
# 데이터 구조
# =========================================================

@dataclass
class ChunkRecord:
    chunk_id: int
    doc_id: int
    doc_path: str
    start: int
    end: int
    text: str
    norm_text: str
    terms_freq: Counter = field(default_factory=Counter)
    length: int = 0
    top_terms: list[str] = field(default_factory=list)


@dataclass
class FileCacheEntry:
    signature: tuple
    text: str


@dataclass
class RAGIndexStore:
    root_path: str
    path_signature: tuple

    docs: dict[int, str] = field(default_factory=dict)
    doc_paths: dict[int, str] = field(default_factory=dict)
    chunks: dict[int, ChunkRecord] = field(default_factory=dict)

    # term -> set(chunk_id)
    postings: dict[str, set] = field(default_factory=lambda: defaultdict(set))

    # BM25
    doc_freq: dict[str, int] = field(default_factory=dict)
    avg_chunk_len: float = 0.0
    total_chunks: int = 0

    # co-occurrence graph
    co_terms: dict[str, Counter] = field(default_factory=lambda: defaultdict(Counter))

    file_cache: dict[str, FileCacheEntry] = field(default_factory=dict)
    query_cache: LRUCache = field(default_factory=lambda: LRUCache(128))


# =========================================================
# 전역 인덱스 레지스트리
# =========================================================

_GLOBAL_RAG_REGISTRY: dict[str, RAGIndexStore] = {}


# =========================================================
# 파일 시스템
# =========================================================

def file_signature(path: str) -> tuple:
    st = os.stat(path)
    return (int(st.st_mtime_ns), int(st.st_size))


def collect_files(path: str) -> list[str]:
    if os.path.isfile(path):
        return [path]

    result = []
    for root, _, files in os.walk(path):
        for name in files:
            result.append(os.path.join(root, name))
    result.sort()
    return result


def directory_signature(path: str) -> tuple:
    files = collect_files(path)
    sigs = []
    for f in files:
        try:
            sigs.append((f, file_signature(f)))
        except OSError:
            continue
    return tuple(sigs)


# =========================================================
# 파일 파서
# =========================================================

def parse_pdf(path: str) -> str:
    doc = fitz.open(path)
    parts = []
    try:
        for page in doc:
            parts.append(page.get_text())
    finally:
        doc.close()
    return "\n".join(parts)


def parse_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def parse_with_unstructured(path: str) -> str:
    elements = partition(filename=path)
    parts = []
    for e in elements:
        text = getattr(e, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def parse_file(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()

    if ext == ".pdf":
        return parse_pdf(path)

    if ext in TEXT_EXTENSIONS:
        return parse_text_file(path)

    return parse_with_unstructured(path)


# =========================================================
# 청크 분할
# =========================================================

def chunk_text(text: str, chunk_chars: int = 1200, overlap_chars: int = 200) -> list[tuple[int, int, str]]:
    text = text or ""
    n = len(text)

    if n == 0:
        return []

    if chunk_chars <= 0:
        chunk_chars = 1200

    if overlap_chars < 0:
        overlap_chars = 0

    step = max(1, chunk_chars - overlap_chars)
    chunks = []

    start = 0
    while start < n:
        end = min(n, start + chunk_chars)

        if end < n:
            window = text[end:min(n, end + 120)]
            match = re.search(r"[\n\.!?]", window)
            if match:
                end = end + match.start() + 1

        piece = text[start:end]
        if piece.strip():
            chunks.append((start, end, piece))

        if end >= n:
            break

        start += step

    return chunks


# =========================================================
# Query weighting / expansion
# =========================================================

def build_weighted_query_terms(query: str, store: RAGIndexStore, max_auto_expand: int = 6) -> dict[str, float]:
    """
    범용 query builder
    1) unigram
    2) bigram
    3) trigram
    4) corpus co-occurrence 기반 자동 확장
    """
    uni, bi, tri = build_query_terms(query)
    weighted: dict[str, float] = {}

    def add(term: str, weight: float):
        if not term:
            return
        if len(term.replace("_", "").replace("__", "")) < 2:
            return
        prev = weighted.get(term, 0.0)
        if weight > prev:
            weighted[term] = weight

    # 핵심 unigram
    for t in uni:
        add(t, 1.0)

    # phrase는 더 강하게
    for t in bi:
        add(t, 1.15)

    for t in tri:
        add(t, 1.25)

    # 코퍼스 기반 자동 확장
    # strong unigram에서 주변 고빈도 co-term을 약하게 추가
    candidate_counter = Counter()
    strong_unigrams = list(dict.fromkeys(uni))[:6]

    for term in strong_unigrams:
        for near_term, cnt in store.co_terms.get(term, {}).items():
            # 이미 query에 있으면 제외
            if near_term in weighted:
                continue

            # ngram은 자동확장에서는 제외
            if "__" in near_term:
                continue

            candidate_counter[near_term] += cnt

    for near_term, cnt in candidate_counter.most_common(max_auto_expand):
        # 문서 전체에 너무 흔한 일반어 제외
        df = store.doc_freq.get(near_term, 0)
        if store.total_chunks > 0:
            df_ratio = df / store.total_chunks
            if df_ratio > 0.6:
                continue
        add(near_term, 0.45)

    # 질문형 보조어: 고정 도메인 사전이 아니라 범용 힌트만
    q = query.lower().strip()
    if q.startswith("how ") or " how " in q:
        for t in ["mechanism", "process", "method"]:
            add(normalize_term(t), 0.22)

    if q.startswith("what ") or " what " in q:
        for t in ["definition", "overview", "concept"]:
            add(normalize_term(t), 0.18)

    if q.startswith("why ") or " why " in q:
        for t in ["reason", "motivation", "benefit"]:
            add(normalize_term(t), 0.18)

    return weighted


# =========================================================
# BM25
# =========================================================

def compute_bm25_score(
    weighted_query_terms: dict[str, float],
    chunk: ChunkRecord,
    doc_freq: dict[str, int],
    total_chunks: int,
    avg_chunk_len: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    score = 0.0

    if total_chunks <= 0 or avg_chunk_len <= 0:
        return 0.0

    for term, q_weight in weighted_query_terms.items():
        tf = chunk.terms_freq.get(term, 0)
        if tf <= 0:
            continue

        df = doc_freq.get(term, 0)
        if df <= 0:
            continue

        idf = math.log(1 + ((total_chunks - df + 0.5) / (df + 0.5)))
        denom = tf + k1 * (1 - b + b * (chunk.length / avg_chunk_len))
        score += q_weight * idf * ((tf * (k1 + 1)) / max(1e-9, denom))

    return score


# =========================================================
# RAG Processor
# =========================================================

class RAGProcessor(BaseProcessor):
    """
    범용 read-only RAG 노드
    - 파일/디렉토리 자동 처리
    - unigram/bigram/trigram 인덱싱
    - 코퍼스 기반 자동 query expansion
    - BM25 랭킹
    """

    def __init__(
        self,
        path: str,
        *,
        chunk_chars: int = 1200,
        overlap_chars: int = 200,
        context_chars: int = 280,
        top_k_chunks: int = 8,
        max_snippets: int = 12,
        query_cache_size: int = 128,
        chunk_top_terms: int = 12,
        auto_expand_terms: int = 6,
    ):
        super().__init__()

        self.path = path
        self.chunk_chars = chunk_chars
        self.overlap_chars = overlap_chars
        self.context_chars = context_chars
        self.top_k_chunks = top_k_chunks
        self.max_snippets = max_snippets
        self.query_cache_size = query_cache_size
        self.chunk_top_terms = chunk_top_terms
        self.auto_expand_terms = auto_expand_terms

    # -------------------------------------------------
    # 인덱스 빌드
    # -------------------------------------------------

    def _get_or_build_store(self) -> RAGIndexStore:
        root = os.path.abspath(self.path)

        if not os.path.exists(root):
            raise FileNotFoundError(f"RAG path not found: {root}")

        current_sig = directory_signature(root)
        existing = _GLOBAL_RAG_REGISTRY.get(root)

        if existing is not None and existing.path_signature == current_sig:
            return existing

        store = self._build_store(root, current_sig)
        _GLOBAL_RAG_REGISTRY[root] = store
        return store

    def _build_store(self, root: str, path_sig: tuple) -> RAGIndexStore:
        store = RAGIndexStore(
            root_path=root,
            path_signature=path_sig,
            query_cache=LRUCache(self.query_cache_size),
        )

        files = collect_files(root)

        doc_id = 0
        chunk_id = 0
        term_df_counter = Counter()
        total_chunk_len = 0

        for file_path in files:
            try:
                sig = file_signature(file_path)

                cached = store.file_cache.get(file_path)
                if cached is not None and cached.signature == sig:
                    text = cached.text
                else:
                    text = parse_file(file_path)
                    store.file_cache[file_path] = FileCacheEntry(signature=sig, text=text)

                text = normalize_space(text)
                if not text:
                    continue

                store.docs[doc_id] = text
                store.doc_paths[doc_id] = file_path

                raw_chunks = chunk_text(
                    text,
                    chunk_chars=self.chunk_chars,
                    overlap_chars=self.overlap_chars,
                )

                for start, end, piece in raw_chunks:
                    uni = build_base_terms(piece)
                    if not uni:
                        continue

                    bi = make_ngrams(uni, 2)
                    tri = make_ngrams(uni, 3)

                    all_terms = []
                    all_terms.extend(uni)
                    all_terms.extend(bi)
                    all_terms.extend(tri)

                    if not all_terms:
                        continue

                    tf = Counter(all_terms)
                    chunk_len = len(all_terms)
                    norm_piece = normalize_space(piece)
                    top_terms = [term for term, _ in Counter(uni).most_common(self.chunk_top_terms)]

                    record = ChunkRecord(
                        chunk_id=chunk_id,
                        doc_id=doc_id,
                        doc_path=file_path,
                        start=start,
                        end=end,
                        text=piece,
                        norm_text=norm_piece,
                        terms_freq=tf,
                        length=chunk_len,
                        top_terms=top_terms,
                    )

                    store.chunks[chunk_id] = record

                    # postings / df
                    for term in tf.keys():
                        store.postings[term].add(chunk_id)
                        term_df_counter[term] += 1

                    # co-occurrence: chunk 내 상위 unigram끼리 연결
                    uniq_top = list(dict.fromkeys(top_terms))
                    for i, t1 in enumerate(uniq_top):
                        for t2 in uniq_top[i+1:]:
                            if t1 == t2:
                                continue
                            store.co_terms[t1][t2] += 1
                            store.co_terms[t2][t1] += 1

                    total_chunk_len += chunk_len
                    chunk_id += 1

                doc_id += 1

            except Exception:
                continue

        store.total_chunks = len(store.chunks)
        store.doc_freq = dict(term_df_counter)
        store.avg_chunk_len = (
            total_chunk_len / store.total_chunks if store.total_chunks > 0 else 0.0
        )

        return store

    # -------------------------------------------------
    # 검색
    # -------------------------------------------------

    def _rank_chunks(self, store: RAGIndexStore, weighted_query_terms: dict[str, float]) -> list[tuple[int, float]]:
        candidate_chunk_ids = set()

        for term in weighted_query_terms.keys():
            candidate_chunk_ids.update(store.postings.get(term, set()))

        if not candidate_chunk_ids:
            return []

        ranked = []
        strong_terms = [t for t, w in weighted_query_terms.items() if w >= 1.0]

        for cid in candidate_chunk_ids:
            chunk = store.chunks[cid]

            score = compute_bm25_score(
                weighted_query_terms=weighted_query_terms,
                chunk=chunk,
                doc_freq=store.doc_freq,
                total_chunks=store.total_chunks,
                avg_chunk_len=store.avg_chunk_len,
            )

            # 강한 term coverage 보정
            if strong_terms:
                coverage = sum(1 for t in strong_terms if t in chunk.terms_freq)
                score += coverage * 0.18

            ranked.append((cid, score))

        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[: self.top_k_chunks]

    def _extract_best_snippet_from_chunk(self, chunk: ChunkRecord, weighted_query_terms: dict[str, float]) -> str:
        text = chunk.text
        lowered = text.lower()
        query_unigrams = {
            t for t in weighted_query_terms.keys()
            if "__" not in t
        }

        hits = []
        pos = 0

        for token in tokenize_raw(lowered):
            idx = lowered.find(token, pos)
            if idx < 0:
                continue

            norm = normalize_term(token)
            if norm in query_unigrams:
                hits.append(idx)

            pos = idx + len(token)

        if not hits:
            return chunk.norm_text

        best_center = hits[0]
        best_score = -1

        for center in hits:
            score = 0
            for h in hits:
                if abs(h - center) <= self.context_chars:
                    score += 1
            if score > best_score:
                best_score = score
                best_center = center

        start = max(0, best_center - self.context_chars)
        end = min(len(text), best_center + self.context_chars)

        return normalize_space(text[start:end])

    def _search(self, store: RAGIndexStore, query: str) -> str:
        weighted_query_terms = build_weighted_query_terms(
            query=query,
            store=store,
            max_auto_expand=self.auto_expand_terms,
        )

        if not weighted_query_terms:
            return ""

        ranked = self._rank_chunks(store, weighted_query_terms)
        if not ranked:
            return ""

        output_parts = []
        seen_chunks = set()
        seen_norm = set()

        for chunk_id, _score in ranked:
            chunk = store.chunks[chunk_id]

            if chunk_id in seen_chunks:
                continue
            seen_chunks.add(chunk_id)

            snippet = self._extract_best_snippet_from_chunk(chunk, weighted_query_terms)
            norm = normalize_space(snippet).lower()

            if not norm or norm in seen_norm:
                continue

            seen_norm.add(norm)

            header = f"[SOURCE] {chunk.doc_path}"
            output_parts.append(f"{header}\n{snippet}")

            if len(output_parts) >= self.max_snippets:
                break

        return "\n\n".join(output_parts)

    # -------------------------------------------------
    # 메인
    # -------------------------------------------------

    async def process(self, data: Any) -> Optional[Any]:
        try:
            query = str(data).strip()

            if not query:
                return ""

            store = self._get_or_build_store()

            cached = store.query_cache.get(query)
            if cached is not None:
                return cached

            result = self._search(store, query)
            store.query_cache.set(query, result)

            return result

        except Exception:
            self.signal("error")
            return ""