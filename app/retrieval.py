"""Re-runnable metadata-preserving ingestion and real OpenRouter vector retrieval.

Offline parsing is available for audits, but never produces a ready vector index.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

import numpy as np
import pymupdf
import yaml
from dotenv import load_dotenv
from jsonschema import Draft202012Validator
from openai import AsyncOpenAI

from .helpdesk_policy import eligible_chunks, resolve_precedence, contextual_chunks, redact

ROOT = Path(__file__).resolve().parents[1]
CHUNKER_VERSION = "sections-pdf-pages-v2-policy-redaction"
EMBEDDING_RATE_PER_MILLION = 0.20  # conservative ceiling, selected text-embedding-3-small


class BudgetExceeded(RuntimeError):
    pass


class BudgetLedger:
    """Durable atomic global budget, including outstanding/unknown reservations."""
    def __init__(self, data_dir: str | Path | None = None, ceiling: float = 2.50):
        self.data_dir = Path(data_dir or os.getenv("APP_DATA_DIR") or os.getenv("HELPDESK_APP_DATA", ROOT / "data"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "spending.sqlite3"
        self.ceiling = min(float(os.getenv("PROJECT_BUDGET_USD", ceiling)), ceiling)
        if not math.isfinite(self.ceiling) or self.ceiling <= 0:
            raise ValueError("Project budget must be finite and positive")
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS spending (id TEXT PRIMARY KEY, kind TEXT, reserved REAL, cost REAL, actual INTEGER, at REAL)")

    @contextmanager
    def _connect(self):
        connection=sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def reserve(self, amount: float, kind: str) -> str:
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Reservation must be positive and finite")
        reservation = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            used = db.execute("SELECT COALESCE(SUM(COALESCE(cost,reserved)),0) FROM spending").fetchone()[0]
            if used + amount > self.ceiling + 1e-12:
                raise BudgetExceeded("Project spending ceiling reached; no external call made")
            db.execute("INSERT INTO spending VALUES (?,?,?,?,?,?)", (reservation, kind, amount, None, 0, time.time()))
        return reservation

    def settle(self, reservation_id: str, cost: float, actual: bool = True) -> None:
        if not math.isfinite(cost) or cost < 0:
            raise ValueError("Cost must be finite and nonnegative")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT reserved,cost FROM spending WHERE id=?", (reservation_id,)).fetchone()
            if not row or row[1] is not None:
                raise ValueError("Unknown or already settled reservation")
            db.execute("UPDATE spending SET cost=?,actual=? WHERE id=?", (cost, int(actual), reservation_id))
            if cost > row[0] + 1e-9:
                # Over-reservation billing mismatch permanently locks further paid calls.
                db.execute("INSERT INTO spending VALUES (?,?,?,?,?,?)", (uuid.uuid4().hex,"billing_mismatch_lock",self.ceiling,None,0,time.time()))

    def snapshot(self) -> dict:
        with self._connect() as db:
            spent, reserved, calculated, count = db.execute("SELECT COALESCE(SUM(cost),0),COALESCE(SUM(CASE WHEN cost IS NULL THEN reserved ELSE 0 END),0),COALESCE(SUM(CASE WHEN actual=0 AND cost IS NOT NULL THEN cost ELSE 0 END),0),COUNT(*) FROM spending").fetchone()
        return {"spent_usd": spent, "reserved_usd": reserved, "remaining_usd": max(0, self.ceiling-spent-reserved), "calculated_cost_usd": calculated,"ceiling_usd": self.ceiling,"calls":count}


def credential() -> str:
    load_dotenv(ROOT / ".env", override=False)
    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key or any(s in key.lower() for s in ("your-key", "your_key", "placeholder", "replace", "changeme")):
        raise RuntimeError("OPENROUTER_API_KEY is absent or a placeholder; real embeddings/chat are blocked")
    return key


def credentials_available() -> bool:
    try:
        credential()
        return True
    except RuntimeError:
        return False


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalise_meta(meta: dict) -> dict:
    return {k: v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else v for k,v in meta.items()}


def parse_documents(root: Path = ROOT) -> tuple[list[dict], list[dict], str]:
    dataset = root / "dataset"
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(json.loads((dataset / "schemas/kb_front_matter.schema.json").read_text(encoding="utf-8")))
    documents, chunks = [], []
    corpus_hash = hashlib.sha256()
    for entry in manifest["documents"]:
        path = dataset / entry["file"]
        raw = path.read_bytes()
        normalized = raw if path.suffix == ".pdf" else raw.replace(b"\r\n",b"\n")
        if _hash(normalized) != entry["sha256"]:
            raise ValueError(f"Source integrity mismatch: {entry['file']}")
        corpus_hash.update(normalized)
        if path.suffix == ".pdf":
            with pymupdf.open(path) as pdf:
                pages = [page.get_text() for page in pdf]
            text = "\n".join(pages)
        else:
            text = raw.decode("utf-8")
            pages = []
        front = re.search(r"(?ms)^---\s*\n(.*?)^---\s*(?:\n|$)", text)
        if not front:
            raise ValueError(f"Missing metadata: {entry['file']}")
        meta = _normalise_meta(yaml.safe_load(front.group(1)))
        validator.validate(meta)
        body = text[front.end():].strip()
        source = str(path.relative_to(root)).replace("\\", "/")
        document = {"metadata":meta,"source_path":source,"source_hash":_hash(normalized),"pages":len(pages) or None}
        documents.append(document)
        if meta["status"] != "current":
            # Retain metadata for all 20, quarantine hostile/unapproved text entirely.
            sections = [("Quarantined source", "Non-current source excluded from model evidence.", [])]
        elif pages:
            # A PDF stays whole to preserve table rows and page-continuation procedures.
            sections = [(meta["title"], body, list(range(1,len(pages)+1)))]
        else:
            split = re.split(r"(?m)^(#{1,3}\s+[^\n]+|\*\*[^\n]+\?\*\*)\n", body)
            sections = []
            if split[0].strip():
                sections.append((meta["title"],split[0].strip(),[]))
            for i in range(1,len(split),2):
                if i+1<len(split) and split[i+1].strip():
                    sections.append((split[i].lstrip("# ").strip(),split[i+1].strip(),[]))
        for i,(section, content, page_numbers) in enumerate(sections):
            text_content = redact(content)
            point = None
            if (meta['id']=='KB-017' and 'phone at home' in section.lower()) or (meta['id']=='SP-002' and 'multi-factor' in section.lower()):
                point = 'mfa_sms'
            if (meta['id']=='KB-017' and 'major incident' in section.lower()) or (meta['id']=='KB-015' and '2. Priorities' in section):
                point = 'p1_threshold'
            chunks.append({"chunk_id":f"{meta['id']}:{i}:{_hash(text_content.encode())[:10]}",
                           "id":meta["id"],"title":meta["title"],"metadata":meta,
                           "source_path":source,"source_hash":document["source_hash"],
                           "content_hash":_hash(text_content.encode()),"section":section,
                           "pages":page_numbers,"text":text_content,"policy_point":point})
    if len(documents) != 20:
        raise ValueError("All 20 supplied documents are required")
    return documents,chunks,corpus_hash.hexdigest()


class Retrieval:
    def __init__(self, data_dir: str | Path | None = None, root: str | Path | None = None):
        self.root = Path(root or ROOT)
        load_dotenv(self.root / ".env",override=False)
        self.data_dir = Path(data_dir or os.getenv("APP_DATA_DIR") or os.getenv("HELPDESK_APP_DATA", self.root / "data"))
        self.data_dir.mkdir(parents=True,exist_ok=True)
        self.model = os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
        self.documents,self.chunks,self.corpus_hash = parse_documents(self.root)
        self.fingerprint = _hash((self.corpus_hash+self.model+CHUNKER_VERSION).encode())
        self.vectors = None
        self.index_path = self.data_dir / "index.npz"
        self.meta_path = self.data_dir / "index.json"
        self.last_audit = {}
        self._load_index()

    def _load_index(self):
        if self.index_path.exists() and self.meta_path.exists():
            metadata=json.loads(self.meta_path.read_text(encoding="utf-8"))
            if metadata.get("fingerprint") == self.fingerprint and metadata.get("provider") == "openrouter":
                with np.load(self.index_path,allow_pickle=False) as loaded:
                    vectors=loaded["vectors"]
                if vectors.ndim==2 and vectors.shape[0]==len(self.chunks) and np.isfinite(vectors).all() and np.all(np.linalg.norm(vectors,axis=1)>0):
                    self.vectors=vectors

    @property
    def ready(self) -> bool:
        return self.vectors is not None

    async def embed(self, texts: list[str], kind: str = "query_embedding") -> np.ndarray:
        key = credential()
        if self.model != "openai/text-embedding-3-small":
            raise RuntimeError("Embedding model pricing is unconfigured; no paid call made")
        # UTF-8 bytes upper bound token count for selected model; no silent truncation.
        token_upper = sum(len(text.encode("utf-8"))+16 for text in texts)
        ceiling = token_upper * EMBEDDING_RATE_PER_MILLION / 1_000_000
        if ceiling > .002 and kind == "query_embedding":
            raise BudgetExceeded("Query embedding exceeds turn budget")
        ledger = BudgetLedger(self.data_dir)
        reservation=ledger.reserve(max(ceiling,.000001),kind)
        client=AsyncOpenAI(api_key=key,base_url=os.getenv("OPENROUTER_BASE_URL","https://openrouter.ai/api/v1"),timeout=20,max_retries=0)
        try:
            response=await client.embeddings.create(model=self.model,input=texts)
            usage=response.usage.model_dump()
            actual=usage.get("cost")
            if actual is None:
                tokens=usage.get("total_tokens")
                if tokens is None:
                    raise RuntimeError("Embedding billing missing; reservation retained and index not saved")
                ledger.settle(reservation,tokens*EMBEDDING_RATE_PER_MILLION/1_000_000,actual=False)
            else:
                ledger.settle(reservation,float(actual),actual=True)
            result=np.array([row.embedding for row in sorted(response.data,key=lambda row:row.index)],dtype=np.float32)
            if result.ndim!=2 or len(result)!=len(texts) or not np.isfinite(result).all() or np.any(np.linalg.norm(result,axis=1)==0):
                raise RuntimeError("Invalid embedding response; no index saved")
            return result
        finally:
            await client.close()

    async def ingest(self, offline: bool = False) -> dict:
        parsed={"fingerprint":self.fingerprint,"model":self.model,"documents":self.documents,"chunks":self.chunks,"chunker":CHUNKER_VERSION}
        (self.data_dir / "parsed.json").write_text(json.dumps(parsed,ensure_ascii=False,indent=2),encoding="utf-8")
        if offline:
            return {"documents":len(self.documents),"chunks":len(self.chunks),"ready":self.ready,"mode":"offline-metadata-only"}
        if self.ready:
            return {"documents":len(self.documents),"chunks":len(self.chunks),"ready":True,"cached":True}
        # Reuse unchanged chunk vectors across corpus edits, keyed by model,
        # chunker and exact embedded bytes, not merely the source filename.
        def embedding_text(chunk):
            return f"{chunk['id']} {chunk['title']} {chunk['section']}\n{chunk['text']}"
        cached={}
        if self.meta_path.exists() and self.index_path.exists():
            old=json.loads(self.meta_path.read_text(encoding='utf-8'))
            if old.get('model')==self.model and old.get('chunker')==CHUNKER_VERSION and old.get('provider')=='openrouter':
                with np.load(self.index_path,allow_pickle=False) as previous:
                    previous_vectors=previous['vectors']
                if len(previous_vectors)==len(old.get('chunks',[])):
                    cached={_hash(embedding_text(chunk).encode()):previous_vectors[i] for i,chunk in enumerate(old['chunks'])}
        texts=[embedding_text(c) for c in self.chunks]
        missing=[i for i,text in enumerate(texts) if _hash(text.encode()) not in cached]
        fresh=await self.embed([texts[i] for i in missing],"ingestion_embedding") if missing else []
        fresh_by_index=dict(zip(missing,fresh))
        vectors=np.array([fresh_by_index[i] if i in fresh_by_index else cached[_hash(text.encode())] for i,text in enumerate(texts)],dtype=np.float32)
        temporary=self.data_dir / "index.tmp.npz"
        np.savez_compressed(temporary,vectors=vectors)
        temporary.replace(self.index_path)
        parsed["provider"]="openrouter"
        self.meta_path.write_text(json.dumps(parsed,ensure_ascii=False),encoding="utf-8")
        self.vectors=vectors
        return {"documents":len(self.documents),"chunks":len(self.chunks),"ready":True,"cached":False,"budget":BudgetLedger(self.data_dir).snapshot()}

    async def search(self, query: str, department: str | None = None, limit: int = 6) -> list[dict]:
        self.last_audit = {}  # never retain an earlier selection after a failed read
        if not self.ready:
            raise RuntimeError("Real embedding index unavailable; run python -m app.retrieval ingest with configured credentials")
        vector=(await self.embed([redact(query)]))[0]
        scores=self.vectors @ vector / (np.linalg.norm(self.vectors,axis=1)*np.linalg.norm(vector))
        candidates=eligible_chunks(self.chunks,department)
        scores_by_id={c["chunk_id"]:float(scores[i]) for i,c in enumerate(self.chunks)}
        codes={code for code in re.findall(r"\b[A-Z]{2,4}-\d{2,4}\b",query.upper()) if code.split('-')[0] not in {'KB','SP','IT','INC'}}
        known_codes={code for d in self.documents for code in d["metadata"]["error_codes"]}
        unknown_codes=codes-known_codes
        def rank(chunk):
            exact=bool(codes & set(re.findall(r"\b[A-Z]{2,4}-\d{2,4}\b",chunk["text"].upper())))
            lexical=len(set(re.findall(r"\w{3,}",query.lower())) & set(re.findall(r"\w{3,}",chunk["text"].lower())))
            return scores_by_id[chunk["chunk_id"]]+(1 if exact else 0)+min(lexical*.015,.20)
        candidates.sort(key=rank,reverse=True)
        selected=candidates[:max(1,min(limit,12))]
        # Governing sources must not disappear merely because vector rank is low.
        governing={"SP-001","SP-002","KB-015","KB-016"}
        if unknown_codes:
            selected=[c for c in selected if c["id"] in governing]
        governing_chunks=[c for c in candidates if c["id"] in governing]
        # An error may occur only in a document's introduction while the actual
        # procedure is in later sections without repeating that code. Vector/top-k
        # selection must not separate a documented error from its own procedure.
        # Use manifest metadata, current/applicable sources only, and preserve the
        # unknown-error barrier so a nearby known code cannot provide a guessed fix.
        error_document_ids={c["id"] for c in candidates
                            if codes.intersection(c["metadata"].get("error_codes", []))}
        error_chunks=[c for c in candidates if c["id"] in error_document_ids] if not unknown_codes else []
        # Keep whole governing/error documents, then resolve conflicting points.
        unique={c["chunk_id"]:c for c in selected+governing_chunks+error_chunks}
        if department == "Finance" and re.search(r"\bvpn\b|nakhlaconnect|\bNX-\d|remote.access|fin.secure", query, re.I):
            # The department exception applies even before an exact error is known.
            unique.update({c["chunk_id"]:c for c in candidates
                           if c["id"] == "KB-002" and c.get("section", "").strip().lower() == "exceptions"})
        result=resolve_precedence(list(unique.values()),department)
        precedence_ids={c["chunk_id"] for c in result}
        result=contextual_chunks(result,department,query)
        selected_source_ids={c.get("parent_chunk_id",c["chunk_id"]) for c in result}
        eligible_ids={c["chunk_id"] for c in candidates}
        selected_audit=[]
        for chunk in result:
            reason=("department_policy_excerpt" if chunk.get("parent_chunk_id") else
                    "governing_policy_closure" if chunk["id"] in governing else
                    "exact_error_document_closure" if chunk["id"] in error_document_ids else "ranked_retrieval")
            selected_audit.append({"chunk_id":chunk["chunk_id"],"id":chunk["id"],"reason":reason,
                                   **({"parent_chunk_id":chunk["parent_chunk_id"]} if chunk.get("parent_chunk_id") else {})})
        excluded=[]
        for chunk in self.chunks:
            cid=chunk["chunk_id"]
            if cid in selected_source_ids:
                continue
            if chunk["metadata"].get("status") != "current":
                reason="non_current_quarantined"
            elif cid not in eligible_ids:
                reason="department_not_applicable"
            elif cid in unique and cid not in precedence_ids:
                reason="conflicting_policy_point_overridden"
            elif cid in precedence_ids:
                reason="department_policy_scope_excluded"
            elif unknown_codes and chunk["id"] not in governing:
                reason="unknown_error_no_adjacent_fix"
            else:
                reason="outside_ranked_or_required_closure"
            excluded.append({"chunk_id":cid,"id":chunk["id"],"status":chunk["metadata"].get("status"),"reason":reason})
        self.last_audit={"department":department,"query_error_codes":sorted(codes),"unknown_error_codes":sorted(unknown_codes),
                         "selected":selected_audit,"excluded":excluded}
        return [{**c,"score":scores_by_id[c.get("parent_chunk_id",c["chunk_id"])],"unknown_error_codes":sorted(unknown_codes)} for c in result]


async def _cli():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=["ingest"])
    parser.add_argument("--offline",action="store_true",help="Parse/audit only; never creates fake vectors")
    args=parser.parse_args()
    result=await Retrieval().ingest(offline=args.offline)
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    asyncio.run(_cli())
