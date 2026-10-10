"""Small reference context engine for replaying transcript failure cases.

The SQLite store is a spike, not a finalized production schema. All retrieval
is scoped to a tenant and session. No model calls occur in this module.
"""

import hashlib
import json
import math
import re
import sqlite3
import time
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Do not remove negation, quantities, names or non-English terms.
STOPWORDS = frozenset('a an the is are was were be been being our we you i it its this that these those '
                     'what who when where how can could would should do does did have has had '
                     'of for to from in on at and or with about as please tell me'.split())

def query_terms(text):
    tokens=[];current=''
    for c in unicodedata.normalize('NFC',text.lower()):
        if unicodedata.category(c)[0] in 'LNM': current+=c
        elif current: tokens.append(current);current=''
    if current: tokens.append(current)
    return list(dict.fromkeys(w for w in tokens if w not in STOPWORDS))[:24]

@dataclass(frozen=True)
class SourceRef:
    id: str
    kind: str
    title: str


@dataclass(frozen=True)
class Segment:
    id: str
    tenant: str
    session: str
    revision: int
    start_ms: int
    end_ms: int
    text: str
    state: str = "final"
    source: str = "system"
    epoch: int = 0
    origin_id: str = 'meeting'


@dataclass(frozen=True)
class Evidence:
    id: str
    revision: int
    start_ms: int
    end_ms: int
    text: str
    source: str
    state: str = "final"
    truncated: bool = False
    origin_id: str = 'meeting'
    origin_kind: str = 'transcript'
    origin_title: str = 'Meeting transcript'


@dataclass(frozen=True)
class Snapshot:
    tenant: str
    session: str
    version: int
    request_id: str
    question: str
    evidence: Tuple[Evidence, ...]
    estimated_tokens: int
    utf8_bytes: int
    truncated: bool
    digest: str
    elapsed_ms: float
    provisional: Tuple[Evidence, ...] = ()
    clarification: Optional[str] = None


def estimated_tokens(text: str) -> int:
    """Heuristic only; deployment must use the selected model's tokenizer."""
    return math.ceil(len(text.encode("utf-8")) / 3)


def clip_utf8(text: str, limit: int) -> str:
    return text.encode("utf-8")[:max(0, limit)].decode("utf-8", errors="ignore")


class ContextStore:
    def __init__(self, path: str = ":memory:") -> None:
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
          PRAGMA foreign_keys=ON;
          CREATE TABLE IF NOT EXISTS sessions (
            tenant TEXT, id TEXT, state TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (tenant, id));
          CREATE TABLE IF NOT EXISTS segments (
            rowid INTEGER PRIMARY KEY, id TEXT, tenant TEXT, session TEXT,
            revision INTEGER, start_ms INTEGER, end_ms INTEGER, text TEXT,
            state TEXT, source TEXT, epoch INTEGER,
            UNIQUE(tenant,session,id),
            FOREIGN KEY(tenant,session) REFERENCES sessions(tenant,id) ON DELETE CASCADE);
          CREATE INDEX IF NOT EXISTS recent_segments ON segments(tenant,session,end_ms);
          CREATE VIRTUAL TABLE IF NOT EXISTS evidence_fts USING fts5(text, tokenize='unicode61');
          CREATE TRIGGER IF NOT EXISTS segments_delete AFTER DELETE ON segments BEGIN
            DELETE FROM evidence_fts WHERE rowid=old.rowid;
          END;
          CREATE TRIGGER IF NOT EXISTS segments_update AFTER UPDATE ON segments BEGIN
            DELETE FROM evidence_fts WHERE rowid=old.rowid;
            INSERT INTO evidence_fts(rowid,text) SELECT new.rowid,new.text WHERE new.state='final';
          END;
          CREATE TRIGGER IF NOT EXISTS segments_insert AFTER INSERT ON segments BEGIN
            INSERT INTO evidence_fts(rowid,text) SELECT new.rowid,new.text WHERE new.state='final';
          END;
          CREATE TABLE IF NOT EXISTS gaps (
            tenant TEXT, session TEXT, start_ms INTEGER, end_ms INTEGER, reason TEXT,
            FOREIGN KEY(tenant,session) REFERENCES sessions(tenant,id) ON DELETE CASCADE);
          CREATE TABLE IF NOT EXISTS source_refs (
            tenant TEXT, session TEXT, id TEXT, kind TEXT, title TEXT,
            PRIMARY KEY(tenant,session,id),
            FOREIGN KEY(tenant,session) REFERENCES sessions(tenant,id) ON DELETE CASCADE);
          CREATE TABLE IF NOT EXISTS segment_origins (
            segment_rowid INTEGER PRIMARY KEY REFERENCES segments(rowid) ON DELETE CASCADE,
            origin_id TEXT NOT NULL);
        """)
        # Additive migration for pre-source-metadata databases.
        self.db.execute("""INSERT OR IGNORE INTO source_refs
            SELECT tenant,id,'meeting','transcript','Meeting transcript' FROM sessions""")
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def start(self, tenant: str, session: str) -> None:
        if not tenant or not session:
            raise ValueError("Tenant and session are required")
        with self.db:
            self.db.execute("INSERT INTO sessions(tenant,id,state) VALUES (?,?,'active')",
                            (tenant, session))
            self.db.execute("INSERT INTO source_refs VALUES (?,?, 'meeting','transcript','Meeting transcript')", (tenant, session))

    def register_source(self, tenant, session, source: SourceRef):
        self.session(tenant, session)
        if not source.id or source.kind not in ('transcript','document') or not source.title.strip():
            raise ValueError('Invalid source reference')
        with self.db:
            self.db.execute('INSERT INTO source_refs VALUES (?,?,?,?,?)',
                            (tenant,session,source.id,source.kind,source.title))
            self.db.execute('UPDATE sessions SET version=version+1 WHERE tenant=? AND id=?',(tenant,session))

    def resolve_source(self, tenant, session, hint):
        self.session(tenant,session)
        rows = self.db.execute('SELECT * FROM source_refs WHERE tenant=? AND session=?',(tenant,session)).fetchall()
        exact = [r for r in rows if r['id'] == hint]
        matches = exact or [r for r in rows if r['title'].casefold() == hint.casefold()]
        return matches[0]['id'] if len(matches)==1 else None

    def source_hint_for_question(self, tenant, session, question):
        self.session(tenant,session)
        titles = [r['title'] for r in self.db.execute('SELECT title FROM source_refs WHERE tenant=? AND session=?', (tenant,session))
                  if re.search(r'(?<!\w)'+re.escape(r['title'])+r'(?!\w)', question, re.IGNORECASE)]
        return titles[0] if len(set(titles))==1 else ('__ambiguous__' if titles else None)

    def session(self, tenant: str, session: str) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM sessions WHERE tenant=? AND id=?",
                              (tenant, session)).fetchone()
        if row is None:
            raise KeyError("Session not found in scope")
        return row

    def transition(self, tenant: str, session: str, action: str) -> None:
        transitions = {("active", "pause"): "paused", ("paused", "resume"): "active",
                       ("active", "stop"): "finalized", ("paused", "stop"): "finalized",
                       ("finalized", "resume"): "active"}
        state = self.session(tenant, session)["state"]
        if (state, action) not in transitions:
            raise ValueError("Invalid session transition: %s -> %s" % (state, action))
        with self.db:
            self.db.execute("UPDATE sessions SET state=?,version=version+1 WHERE tenant=? AND id=?",
                            (transitions[(state, action)], tenant, session))

    def ingest(self, seg: Segment, correction: bool = False) -> bool:
        if self.session(seg.tenant, seg.session)["state"] != "active":
            raise ValueError("Capture is not active")
        if (seg.revision < 0 or seg.start_ms < 0 or seg.end_ms < seg.start_ms
                or seg.epoch < 0 or seg.state not in ("partial", "final")
                or seg.source not in ("mic", "system") or not seg.id):
            raise ValueError("Invalid segment")
        prior = self.db.execute("SELECT * FROM segments WHERE tenant=? AND session=? AND id=?",
                                (seg.tenant, seg.session, seg.id)).fetchone()
        if self.resolve_source(seg.tenant,seg.session,seg.origin_id) != seg.origin_id:
            raise ValueError('Unknown source reference')
        values = (seg.revision, seg.start_ms, seg.end_ms, seg.text, seg.state, seg.source, seg.epoch)
        if prior is not None:
            if seg.revision < prior["revision"]:
                return False
            origin = self.db.execute('SELECT origin_id FROM segment_origins WHERE segment_rowid=?',(prior['rowid'],)).fetchone()
            if seg.origin_id != (origin['origin_id'] if origin else 'meeting'):
                raise ValueError('A segment cannot change origin')
            old = tuple(prior[k] for k in ("revision", "start_ms", "end_ms", "text", "state", "source", "epoch"))
            if seg.revision == prior["revision"]:
                if old != values:
                    raise ValueError("Conflicting payload for the same revision")
                return False
            if prior["state"] == "final" and (not correction or seg.state != "final"):
                raise ValueError("Finalized segments require an explicit final correction")
            if seg.source != prior["source"] or seg.epoch != prior["epoch"]:
                raise ValueError("A segment cannot change audio source or epoch")
        with self.db:
            self.db.execute("""INSERT INTO segments
                (id,tenant,session,revision,start_ms,end_ms,text,state,source,epoch)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(tenant,session,id) DO UPDATE SET
                revision=excluded.revision,start_ms=excluded.start_ms,end_ms=excluded.end_ms,
                text=excluded.text,state=excluded.state,source=excluded.source,epoch=excluded.epoch""",
                (seg.id, seg.tenant, seg.session) + values)
            rowid = self.db.execute('SELECT rowid FROM segments WHERE tenant=? AND session=? AND id=?', (seg.tenant,seg.session,seg.id)).fetchone()[0]
            self.db.execute('INSERT OR IGNORE INTO segment_origins VALUES (?,?)', (rowid,seg.origin_id))
            self.db.execute("UPDATE sessions SET version=version+1 WHERE tenant=? AND id=?",
                            (seg.tenant, seg.session))
        return True

    def discard_provisional(self, tenant, session, source, epoch):
        self.session(tenant,session)
        with self.db:
            removed=self.db.execute("DELETE FROM segments WHERE tenant=? AND session=? AND source=? AND epoch=? AND state='partial'",
                                    (tenant,session,source,epoch)).rowcount
            if removed:self.db.execute('UPDATE sessions SET version=version+1 WHERE tenant=? AND id=?',(tenant,session))
        return removed

    def gap(self, tenant: str, session: str, start_ms: int, end_ms: int, reason: str) -> None:
        self.session(tenant, session)
        if start_ms < 0 or end_ms < start_ms or not reason:
            raise ValueError("Invalid gap")
        with self.db:
            self.db.execute("INSERT INTO gaps VALUES (?,?,?,?,?)",
                            (tenant, session, start_ms, end_ms, reason))
            self.db.execute("UPDATE sessions SET version=version+1 WHERE tenant=? AND id=?",
                            (tenant, session))

    def gaps(self, tenant: str, session: str) -> List[dict]:
        self.session(tenant, session)
        return [dict(r) for r in self.db.execute(
            "SELECT start_ms,end_ms,reason FROM gaps WHERE tenant=? AND session=? ORDER BY start_ms",
            (tenant, session))]

    def transcript(self, tenant: str, session: str) -> List[dict]:
        self.session(tenant, session)
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM segments WHERE tenant=? AND session=? ORDER BY start_ms,id", (tenant, session))]

    def fact_signature(self,tenant,session):
        """Final facts, source identity, gaps and lifecycle; partial churn is excluded."""
        state=self.session(tenant,session)['state']
        finals=[tuple(row) for row in self.db.execute("SELECT id,revision FROM segments WHERE tenant=? AND session=? AND state='final' ORDER BY id",(tenant,session))]
        sources=[tuple(row) for row in self.db.execute('SELECT id,kind,title FROM source_refs WHERE tenant=? AND session=? ORDER BY id',(tenant,session))]
        return hashlib.sha256(json.dumps([state,finals,sources,self.gaps(tenant,session)],sort_keys=True).encode()).hexdigest()

    def retrieve(self, tenant: str, session: str, query: str, limit: int = 5, source_hint=None) -> List[Evidence]:
        self.session(tenant, session)
        if not 1 <= limit <= 100:
            raise ValueError("Retrieval limit must be 1..100")
        words = query_terms(query)
        scope = self.resolve_source(tenant,session,source_hint) if source_hint is not None else None
        if source_hint is not None and scope is None: return []
        if not words:
            return []
        match = " OR ".join('"' + w.replace('"', '""') + '"' for w in words)
        rows = self.db.execute("""SELECT s.*,bm25(evidence_fts) AS relevance FROM evidence_fts
            JOIN segments s ON s.rowid=evidence_fts.rowid
            LEFT JOIN segment_origins o ON o.segment_rowid=s.rowid
            WHERE evidence_fts MATCH ? AND s.tenant=? AND s.session=? AND s.state='final'
            AND (? IS NULL OR coalesce(o.origin_id,'meeting')=?)
            ORDER BY bm25(evidence_fts),s.end_ms DESC,s.id LIMIT 1000""",
            (match, tenant, session, scope,scope)).fetchall()
        rows = sorted(rows,key=lambda r:(-len(set(words)&set(query_terms(r['text']))),r['relevance'],-r['end_ms'],r['id']))[:limit]
        return [self._evidence(row) for row in rows]

    def _evidence(self, row: sqlite3.Row) -> Evidence:
        origin=self.db.execute('''SELECT r.* FROM source_refs r LEFT JOIN segment_origins o
            ON o.origin_id=r.id AND o.segment_rowid=? WHERE r.tenant=? AND r.session=?
            AND r.id=coalesce((SELECT origin_id FROM segment_origins WHERE segment_rowid=?),'meeting')''',
            (row['rowid'],row['tenant'],row['session'],row['rowid'])).fetchone()
        return Evidence(row["id"], row["revision"], row["start_ms"], row["end_ms"],
                        row["text"], row["source"], row["state"], False,
                        origin['id'],origin['kind'],origin['title'])

    def freeze(self, tenant: str, session: str, request_id: str, question: str,
               token_budget: int = 1800, recent_count: int = 12,
               max_utf8_bytes: int = 5400, source_hint=None, include_recent=False) -> Snapshot:
        started = time.perf_counter()
        if token_budget < 64 or max_utf8_bytes < 64 or recent_count < 0 or not request_id:
            raise ValueError("Invalid snapshot budget/request")
        state = self.session(tenant, session)
        hard_limit = min(max_utf8_bytes, token_budget * 3)
        # Reserve room for evidence: an overlong question is explicitly truncated.
        clipped_question = clip_utf8(question, hard_limit // 2)
        scope = self.resolve_source(tenant,session,source_hint) if source_hint is not None else None
        clarification = 'Specify one available source; the requested source is missing or ambiguous.' if source_hint is not None and scope is None else None
        used = len(clipped_question.encode("utf-8"))
        truncated = clipped_question != question
        recent = self.db.execute("""SELECT s.* FROM segments s LEFT JOIN segment_origins o ON o.segment_rowid=s.rowid
            WHERE tenant=? AND session=? AND (? IS NULL OR coalesce(o.origin_id,'meeting')=?)
            ORDER BY end_ms DESC,id LIMIT ?""", (tenant, session,scope,scope,recent_count)).fetchall() if not clarification else []
        selected: List[Evidence] = []
        seen = set()
        # Relevant final facts first. Recent context is an explicit option;
        # provisional text is represented separately below.
        candidates = self.retrieve(tenant, session, clipped_question, source_hint=source_hint)
        # Explicitly selected documents may need their full short context even
        # when query wording differs from the document's vocabulary.
        if scope is not None:
            candidates += [self._evidence(r) for r in recent if r['state']=='final']
        elif include_recent:
            candidates += [self._evidence(r) for r in recent if r['state']=='final']
        for e in candidates:
            if e.id in seen:
                continue
            seen.add(e.id)
            label = "[%s@%s %s %s %s-%s] " % (e.id, e.revision, e.source, e.state, e.start_ms, e.end_ms)
            room = hard_limit - used - len(label.encode("utf-8")) - 1
            if room < 32:
                truncated = True
                continue
            text = clip_utf8(e.text, room)
            is_clipped = text != e.text
            selected.append(Evidence(e.id, e.revision, e.start_ms, e.end_ms,
                                     text, e.source, e.state, is_clipped))
            selected[-1] = Evidence(**{**selected[-1].__dict__, 'origin_id':e.origin_id,
                                       'origin_kind':e.origin_kind,'origin_title':e.origin_title})
            used += len((label + text + "\n").encode("utf-8"))
            truncated = truncated or is_clipped
        provisional=[]
        for r in recent:
            if r['state']!='partial': continue
            e=self._evidence(r); room=hard_limit-used-128
            if room<32: truncated=True; continue
            text=clip_utf8(e.text,room)
            provisional.append(Evidence(**{**e.__dict__,'text':text,'truncated':text!=e.text}))
            used+=len(text.encode())+128
        canonical = json.dumps({"tenant": tenant, "session": session,
            "version": state["version"], "question": clipped_question,
            "evidence": [e.__dict__ for e in selected], 'provisional':[e.__dict__ for e in provisional],
            'clarification':clarification}, ensure_ascii=False, sort_keys=True)
        return Snapshot(tenant, session, state["version"], request_id, clipped_question,
                        tuple(selected), math.ceil(used / 3), used, truncated,
                        hashlib.sha256(canonical.encode()).hexdigest(),
                        (time.perf_counter() - started) * 1000, tuple(provisional),clarification)

    def delete(self, tenant: str, session: str) -> None:
        self.session(tenant, session)
        with self.db:
            self.db.execute("DELETE FROM sessions WHERE tenant=? AND id=?", (tenant, session))


class RequestGate:
    """Prevent delayed responses from older triggers overwriting the current one."""
    def __init__(self) -> None:
        self.current: Optional[str] = None

    def begin(self, request_id: str) -> None:
        if not request_id:
            raise ValueError("Request ID required")
        self.current = request_id

    def cancel(self) -> None:
        self.current = None

    def accepts(self, request_id: str) -> bool:
        return self.current is not None and request_id == self.current
