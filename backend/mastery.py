# mastery.py  ––  semantic-search version
# ----------------------------------------------------------------------
import sqlite3, pathlib, time, threading, struct
from contextlib import contextmanager
from typing import List, Dict, Tuple, Optional

import numpy as np
from sentence_transformers import SentenceTransformer
import faiss                     # CPU build is fine for small indices
import logging

# Set up a module-level logger. Users can configure logging level externally.
logger = logging.getLogger(__name__)

DB_PATH = pathlib.Path(__file__).with_suffix(".db")

# ─────────────────────────────── embeddings & index ────────────────────
EMBEDDER = SentenceTransformer("intfloat/e5-small-v2")
EMBED_DIM = EMBEDDER.get_sentence_embedding_dimension()
FAISS_LOCK = threading.Lock()          # protects index rebuild / search
FAISS_INDEX: Optional[faiss.IndexFlatIP] = None   # built lazily

# ------------------------------------------------------------------ #
# 1 .  Low-level storage helpers                                    #
# ------------------------------------------------------------------ #
@contextmanager
def _conn(path: pathlib.Path = DB_PATH):
    with sqlite3.connect(path) as cx:
        cx.execute("PRAGMA journal_mode=WAL")
        yield cx
        cx.commit()

def _init_schema() -> None:
    with _conn() as cx:
        cx.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
              user_id     TEXT,
              concept     TEXT,
              weight      REAL,
              ts          INTEGER
            );
            CREATE TABLE IF NOT EXISTS concepts (
              concept   TEXT PRIMARY KEY,
              canonical TEXT,
              embedding BLOB           
            );
            """
        )

_init_schema()

# ------------------------------------------------------------------ #
# 2 .  Helpers: embeddings & FAISS                                   #
# ------------------------------------------------------------------ #
def _embed(text: str) -> np.ndarray:
    """Return a **normalised** 384-float32 vector."""
    vec = EMBEDDER.encode(text, normalize_embeddings=True)
    return vec.astype(np.float32)

def _bytes_to_vec(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)

def _rebuild_faiss() -> None:
    """Reload all embeddings from DB into a single in-memory index."""
    global FAISS_INDEX
    with _conn() as cx:
        rows = cx.execute("SELECT concept, embedding FROM concepts "
                          "WHERE embedding IS NOT NULL").fetchall()
    if not rows:
        FAISS_INDEX = None
        return

    vecs = np.vstack([_bytes_to_vec(b) for _, b in rows])
    index = faiss.IndexFlatIP(EMBED_DIM)      # dot-product on normed vecs == cosine
    index.add(vecs)
    index.concepts = [c for c, _ in rows]     # store list for lookup
    FAISS_INDEX = index

def _upsert_concept(concept: str) -> None:
    """Ensure concept exists with embedding; rebuild FAISS if new."""
    with _conn() as cx:
        row = cx.execute("SELECT embedding FROM concepts WHERE concept=?",
                         (concept,)).fetchone()
        if row:
            return                         # already known

        vec = _embed(concept)
        cx.execute("INSERT INTO concepts (concept, canonical, embedding) "
                   "VALUES (?,?,?)",
                   (concept, concept, vec.tobytes()))

    with FAISS_LOCK:
        _rebuild_faiss()                  # refresh index

# ------------------------------------------------------------------ #
# 3 .  Public API                                                    #
# ------------------------------------------------------------------ #
_EVENT_WEIGHTS = {
    "confusion":       -1.0,
    "assumed_mastery": +0.1,
    "recall_correct":  +1.0,
    "recall_fail":     -1.0,
}

def add_event(
    user_id: str,
    concept: str,
    event_type: str,
    weight: float | None = None,
    ts: int | None = None,
) -> None:
    """Log a learning signal and make sure the concept is embedded."""
    if event_type not in _EVENT_WEIGHTS and weight is None:
        raise ValueError(f"Unknown event_type={event_type!r}")

    w  = _EVENT_WEIGHTS.get(event_type) if weight is None else weight
    ts = ts or int(time.time())
    concept = concept.lower().strip()

    _upsert_concept(concept)

    with _conn() as cx:
        cx.execute(
            "INSERT INTO events (user_id, concept, weight, ts) "
            "VALUES (?,?,?,?)",
            (user_id, concept, w, ts),
        )

def mastery_scores(
    user_id: str,
    half_life_days: float = 30.0,
) -> Dict[str, float]:
    """Fold events → score in [0,1] per concept (exponential decay)."""
    decay_lambda = 0.69314718 / (half_life_days * 86_400)
    now = int(time.time())

    with _conn() as cx:
        rows = cx.execute(
            "SELECT concept, SUM(weight * EXP(-? * (? - ts))) "
            "FROM events WHERE user_id=? GROUP BY concept",
            (decay_lambda, now, user_id),
        ).fetchall()

    def squash(x: float) -> float:          # logistic
        return 1 / (1 + pow(2.71828, -x))

    return {c: squash(v) for c, v in rows}

# ------------------------------------------------------------------ #
# 4 .  Nearest-neighbour fallback                                   #
# ------------------------------------------------------------------ #
def _nearest_score(phrase: str,
                   scores: Dict[str, float],
                   default: float = -0.5,
                   *,
                   log: bool = False) -> float:
    """Return score of closest known concept *weighted* by cosine sim.
    When *log* is True, the neighbour, similarity, and weighted score are
    emitted via the module logger at DEBUG level.
    """
    if FAISS_INDEX is None:
        if log:
            logger.debug("%s → [no index] default %.2f", phrase, default)
        return default

    vec = _embed(phrase)
    with FAISS_LOCK:
        D, I = FAISS_INDEX.search(vec[None, :], 1)   # top-1
    sim = float(D[0][0])             # cosine in [-1,1] (normed)
    idx = int(I[0][0])

    if sim < 0.2:                   # similarity too low → unknown
        if log:
            logger.debug("%s → [sim %.2f < 0.55] default %.2f", phrase, sim, default)
        return default

    neighbour = FAISS_INDEX.concepts[idx]
    neighbour_score = scores.get(neighbour, default)
    score = (neighbour_score * sim) + (default * (1 - sim))

    print(f"phrase: {phrase}, neighbour: {neighbour}, sim: {sim}, score: {score}")
    if log:
        logger.debug("%s → neighbour %s (sim %.2f) => score %.2f", phrase, neighbour, sim, score)

    return score

# ------------------------------------------------------------------ #
# 5 .  Classification helper                                        #
# ------------------------------------------------------------------ #

def classify(
    user_id: str,
    phrases: List[str],
    weak_thresh: float = 0.4,
    strong_thresh: float = 0.7,
    *,
    debug: bool = False,
) -> Tuple[List[str], List[str], List[str]]:
    """
    Return three lists: (weak, strong, neutral).
    Unknown phrases borrow the nearest neighbour's score.

    When *debug* is True, the closest neighbour information for each
    unknown phrase is logged at DEBUG level. Enable it with::

        import logging, mastery
        logging.basicConfig(level=logging.DEBUG)
        weak, strong, neutral = mastery.classify(user, phrases, debug=True)
    """
    scores = mastery_scores(user_id)
    weak, strong, neutral = [], [], []

    for p in phrases:
        key = p.lower().strip()
        s = scores.get(key)
        print(f"key: {key}, s: {s}")
        if s is None:
            # Log neighbour details if debug is True
            s = _nearest_score(key, scores, log=debug)

        if s < weak_thresh:
            weak.append(p)
        elif s > strong_thresh:
            strong.append(p)
        else:
            neutral.append(p)

    return weak, strong, neutral

# ------------------------------------------------------------------ #
# 6 .  Demo                                                         #
# ------------------------------------------------------------------ #
if __name__ == "__main__":
    USER = "alice"

    # # Simulate user interactions
    add_event(USER, "priors",          "confusion")
    add_event(USER, "posterior",       "confusion")
    add_event(USER, "gradient descent","assumed_mastery")
    add_event(USER, "gradient descent","recall_correct")

    weak, strong, neutral = classify(
        USER,
        ["tensor calculus", "duck", "bayes rule", "cheesecake"],
        debug=True
    )

    print("Weak   :", weak)
    print("Strong :", strong)
    print("Neutral:", neutral)