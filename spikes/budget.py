"""Shared usage/cash limits with conservative reservations and no automatic refunds.

Reported costs are list-price estimates until reconciled to invoices. Failed
or interrupted requests retain their reservation when billing is unknown.
"""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sqlite3
import uuid

AUTHORIZED_CEILING = Decimal('2.00')
AUTHORIZED_USAGE_CEILING = Decimal('10.00')


class BudgetLedger:
    def __init__(self, path: Path, ceiling: str = '2.00', coverage=None, cash_ceiling='2.00'):
        self.ceiling = Decimal(ceiling)
        self.coverage = coverage or {}
        cash = Decimal(cash_ceiling)
        if not self.ceiling.is_finite() or not cash.is_finite():
            raise ValueError('Budget must be finite')
        self.cash_ceiling = min(cash, self.ceiling)
        maximum = AUTHORIZED_USAGE_CEILING if self.coverage else AUTHORIZED_CEILING
        if (not self.ceiling.is_finite() or not 0 < self.ceiling <= maximum
                or not self.cash_ceiling.is_finite() or not 0 < self.cash_ceiling <= AUTHORIZED_CEILING):
            raise ValueError('Invalid authorized usage/cash ceiling')
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute('''CREATE TABLE IF NOT EXISTS requests (
            id TEXT PRIMARY KEY, provider TEXT, reserved TEXT, reported TEXT,
            state TEXT NOT NULL, created_at TEXT NOT NULL)''')
        columns = {r['name'] for r in self.db.execute('PRAGMA table_info(requests)')}
        if 'coverage' not in columns:
            self.db.execute("ALTER TABLE requests ADD COLUMN coverage TEXT NOT NULL DEFAULT 'unknown'")
        self.db.execute('''CREATE TABLE IF NOT EXISTS reconciliations (
            request_id TEXT PRIMARY KEY, prior_state TEXT, prior_reported TEXT,
            reported TEXT NOT NULL, evidence_ref TEXT NOT NULL, reconciled_at TEXT NOT NULL)''')
        self.db.commit()

    def close(self):
        self.db.close()

    def exposure(self):
        total = Decimal(0)
        for row in self.db.execute('SELECT reserved,reported,state FROM requests'):
            # Failed/unknown/pending calls retain the full reservation.
            if row['state'] == 'complete':
                total += Decimal(row['reported'])
            elif row['state'] == 'overrun':
                total += max(Decimal(row['reported']), Decimal(row['reserved']))
            else:
                total += Decimal(row['reserved'])
        return total

    def reserve(self, provider: str, amount: str) -> str:
        value = Decimal(amount)
        if not value.is_finite() or value <= 0:
            raise ValueError('Reservation must be positive and finite')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            if self.db.execute("SELECT 1 FROM requests WHERE state='overrun' LIMIT 1").fetchone():
                raise ValueError('A pricing overrun requires reconciliation before another call')
            if self.exposure() + value > self.ceiling:
                raise ValueError('Approved cumulative API budget would be exceeded')
            policy = self.coverage.get(provider, {})
            classification = policy.get('kind', 'unknown') if policy.get('verified') else 'unknown'
            if classification not in ('free', 'credit', 'unknown'):
                raise ValueError('Invalid coverage classification')
            if classification == 'credit':
                balance = Decimal(policy.get('balance_usd', '0'))
                if not balance.is_finite() or balance < 0:
                    raise ValueError('Invalid verified credit balance')
                consumed = sum((self._amount(r) for r in self.db.execute(
                    "SELECT * FROM requests WHERE provider=? AND coverage='credit'", (provider,))), Decimal(0))
                if consumed + value > balance:
                    raise ValueError('Verified provider credits would be exceeded')
            if self.cash_exposure() + (value if classification == 'unknown' else Decimal(0)) > self.cash_ceiling:
                raise ValueError('Approved possible cash exposure would be exceeded')
            request_id = str(uuid.uuid4())
            self.db.execute('''INSERT INTO requests
                (id,provider,reserved,reported,state,created_at,coverage) VALUES (?,?,?,NULL,?,?,?)''',
                            (request_id, provider, str(value), 'pending', datetime.now(timezone.utc).isoformat(), classification))
            self.db.commit()
            return request_id
        except Exception:
            self.db.rollback()
            raise

    def settle(self, request_id: str, reported_cost: Decimal) -> None:
        if not reported_cost.is_finite() or reported_cost < 0:
            raise ValueError('Reported cost must be nonnegative and finite')
        with self.db:
            row = self.db.execute('SELECT * FROM requests WHERE id=?', (request_id,)).fetchone()
            if row is None or row['state'] != 'pending':
                raise ValueError('Reservation missing or already closed')
            state = 'complete' if reported_cost <= Decimal(row['reserved']) else 'overrun'
            self.db.execute('UPDATE requests SET reported=?,state=? WHERE id=?',
                            (str(reported_cost), state, request_id))
        if state == 'overrun':
            raise RuntimeError('Usage exceeded the conservative reservation; stop and reconcile pricing')

    def unknown(self, request_id: str) -> None:
        with self.db:
            self.db.execute("UPDATE requests SET state='unknown' WHERE id=? AND state='pending'", (request_id,))

    def reconcile(self, request_id, reported_cost, evidence_ref):
        """Record independently verified usage; never refund on a guess or timeout.

        evidence_ref identifies a locally inspected usage/invoice record. Coverage
        remains historical. This never changes billing or clears benchmark halts.
        """
        if not reported_cost.is_finite() or reported_cost<0 or not evidence_ref.strip() or len(evidence_ref)>512:
            raise ValueError('Verified nonnegative usage and an evidence reference are required')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT * FROM requests WHERE id=?',(request_id,)).fetchone()
            if row is None or row['state'] not in ('unknown','overrun'):
                raise ValueError('Only unresolved closed requests can be reconciled')
            self.db.execute('INSERT INTO reconciliations VALUES (?,?,?,?,?,?)',
                (request_id,row['state'],row['reported'],str(reported_cost),evidence_ref,datetime.now(timezone.utc).isoformat()))
            self.db.execute("UPDATE requests SET reported=?,state='complete' WHERE id=?",(str(reported_cost),request_id))
            self.db.commit()
        except Exception:
            self.db.rollback();raise

    def summary(self) -> dict:
        return {'authorized_ceiling_usd': str(self.ceiling),
                'estimated_or_reserved_exposure_usd': str(self.exposure()),
                'possible_cash_exposure_usd': str(self.cash_exposure()),
                'authorized_cash_ceiling_usd': str(self.cash_ceiling),
                'covered_usage_usd': str(sum((self._amount(r) for r in self.db.execute(
                    "SELECT * FROM requests WHERE coverage IN ('free','credit')")), Decimal(0))),
                'requests': [dict(r) for r in self.db.execute('SELECT * FROM requests ORDER BY created_at')],
                'invoice_reconciled': False}

    @staticmethod
    def _amount(row):
        if row['state'] == 'complete': return Decimal(row['reported'])
        if row['state'] == 'overrun': return max(Decimal(row['reserved']), Decimal(row['reported']))
        return Decimal(row['reserved'])

    def cash_exposure(self):
        # Historical classifications are never retroactively changed by a policy.
        return sum((self._amount(r) for r in self.db.execute(
            "SELECT * FROM requests WHERE coverage='unknown' OR state IN ('unknown','overrun')")), Decimal(0))
