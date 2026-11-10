"""Money trail analysis: turn a transaction ledger into a graph and look for
patterns forensic accountants check by hand.

Signals:
  round-trip-cycle         money that travels in a loop back to where it started
  pass-through             an account that receives funds and quickly forwards most of them
  structuring              several transfers kept just under a review threshold
  unusual-amount-for-payee a payment far above what this payer normally sends this payee
  statistical-outlier      Isolation Forest outliers over simple per-transaction features
"""

from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import median

import networkx as nx
import numpy as np
from sklearn.ensemble import IsolationForest

from .base import Finding

REQUIRED_COLUMNS = {"txn_id", "timestamp", "from_account", "to_account", "amount"}


@dataclass
class Transaction:
    txn_id: str
    timestamp: datetime
    from_account: str
    to_account: str
    amount: float
    memo: str = ""
    from_name: str = ""
    to_name: str = ""

    @property
    def locator(self) -> str:
        return f"txn:{self.txn_id}"

    def as_text(self) -> str:
        memo = f' "{self.memo}"' if self.memo else ""
        return (
            f"{self.txn_id} {self.timestamp.isoformat(timespec='minutes')} "
            f"{self.from_account} -> {self.to_account} {self.amount:.2f}{memo}"
        )

    def to_dict(self) -> dict:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


def load_transactions(path: str | Path) -> list[Transaction]:
    with open(path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"transactions file is missing columns: {sorted(missing)}")
        rows = [
            Transaction(
                txn_id=row["txn_id"].strip(),
                timestamp=datetime.fromisoformat(row["timestamp"].strip()),
                from_account=row["from_account"].strip(),
                to_account=row["to_account"].strip(),
                amount=float(row["amount"]),
                memo=(row.get("memo") or "").strip(),
                from_name=(row.get("from_name") or "").strip(),
                to_name=(row.get("to_name") or "").strip(),
            )
            for row in reader
        ]
    return sorted(rows, key=lambda t: t.timestamp)


def build_graph(transactions: list[Transaction]) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    for txn in transactions:
        graph.add_edge(txn.from_account, txn.to_account, key=txn.txn_id, txn=txn)
    return graph


def _money(value: float) -> str:
    return f"{value:,.2f}"


def find_round_trips(transactions: list[Transaction], exhibit_id: str, window_days: int = 14, max_len: int = 4) -> list[Finding]:
    """Cycles in the payment graph that can be walked forward in time."""
    simple = nx.DiGraph()
    by_edge: dict[tuple[str, str], list[Transaction]] = {}
    for txn in transactions:
        simple.add_edge(txn.from_account, txn.to_account)
        by_edge.setdefault((txn.from_account, txn.to_account), []).append(txn)

    findings = []
    for cycle in nx.simple_cycles(simple, length_bound=max_len):
        if len(cycle) < 2:
            continue
        # Try each rotation so the walk can start at any account in the loop.
        best: list[Transaction] | None = None
        for start in range(len(cycle)):
            order = cycle[start:] + cycle[:start]
            hops = list(zip(order, order[1:] + order[:1]))
            chain: list[Transaction] = []
            last_time = None
            for source, target in hops:
                options = [t for t in by_edge[(source, target)] if last_time is None or t.timestamp >= last_time]
                if not options:
                    chain = []
                    break
                pick = min(options, key=lambda t: t.timestamp)
                chain.append(pick)
                last_time = pick.timestamp
            if chain and chain[-1].timestamp - chain[0].timestamp <= timedelta(days=window_days):
                if best is None or chain[-1].timestamp - chain[0].timestamp < best[-1].timestamp - best[0].timestamp:
                    best = chain
        if best:
            path = " -> ".join([best[0].from_account] + [t.to_account for t in best])
            span_hours = (best[-1].timestamp - best[0].timestamp).total_seconds() / 3600
            findings.append(
                Finding(
                    exhibit_id=exhibit_id,
                    analyzer="money",
                    signal="round-trip-cycle",
                    title="Money moved in a loop back to its starting account",
                    detail=f"{path} within {span_hours:.0f} hours via {', '.join(t.txn_id for t in best)}.",
                    locator=best[0].locator,
                    confidence="medium",
                    limitations="Loops also happen with refunds, shared expenses and loan repayments. Check the memos and the people involved.",
                    data={"path": path, "txn_ids": [t.txn_id for t in best]},
                )
            )
    return findings


def find_pass_through(
    transactions: list[Transaction],
    exhibit_id: str,
    hours: int = 48,
    share: float = 0.8,
    busy_account_txns: int = 15,
) -> list[Finding]:
    findings = []
    incoming: dict[str, list[Transaction]] = {}
    outgoing: dict[str, list[Transaction]] = {}
    for txn in transactions:
        incoming.setdefault(txn.to_account, []).append(txn)
        outgoing.setdefault(txn.from_account, []).append(txn)
    for account, received in incoming.items():
        # Busy accounts (a shop's current account, payroll) move money in and
        # out all day, so this pattern means little for them.
        if len(received) + len(outgoing.get(account, [])) > busy_account_txns:
            continue
        for inflow in received:
            window_end = inflow.timestamp + timedelta(hours=hours)
            forwarded = [
                t for t in outgoing.get(account, []) if inflow.timestamp <= t.timestamp <= window_end
            ]
            total_out = sum(t.amount for t in forwarded)
            if forwarded and total_out >= share * inflow.amount and inflow.amount >= 1000:
                findings.append(
                    Finding(
                        exhibit_id=exhibit_id,
                        analyzer="money",
                        signal="pass-through",
                        title="Account forwarded most of an incoming payment within hours",
                        detail=(
                            f"{account} received {_money(inflow.amount)} in {inflow.txn_id} and sent out "
                            f"{_money(total_out)} ({total_out / inflow.amount:.0%}) within {hours} hours "
                            f"via {', '.join(t.txn_id for t in forwarded)}."
                        ),
                        locator=inflow.locator,
                        confidence="medium",
                        limitations="Payment processors, agents and family accounts also forward money quickly.",
                        data={"account": account, "inflow": inflow.txn_id, "outflows": [t.txn_id for t in forwarded]},
                    )
                )
                break
    return findings


def find_structuring(
    transactions: list[Transaction],
    exhibit_id: str,
    threshold: float = 10_000,
    band: float = 0.15,
    window_days: int = 7,
    min_count: int = 3,
) -> list[Finding]:
    findings = []
    near = [t for t in transactions if threshold * (1 - band) <= t.amount < threshold]
    pairs: dict[tuple[str, str], list[Transaction]] = {}
    for txn in near:
        pairs.setdefault((txn.from_account, txn.to_account), []).append(txn)
    for (source, target), group in pairs.items():
        group.sort(key=lambda t: t.timestamp)
        for i in range(len(group)):
            window = [t for t in group[i:] if t.timestamp - group[i].timestamp <= timedelta(days=window_days)]
            if len(window) >= min_count:
                total = sum(t.amount for t in window)
                findings.append(
                    Finding(
                        exhibit_id=exhibit_id,
                        analyzer="money",
                        signal="structuring",
                        title=f"{len(window)} transfers kept just under the {_money(threshold)} review threshold",
                        detail=(
                            f"{source} -> {target}: {', '.join(f'{t.txn_id} ({_money(t.amount)})' for t in window)}, "
                            f"total {_money(total)} within {window_days} days."
                        ),
                        locator=window[0].locator,
                        confidence="medium",
                        limitations="Some people split payments for ordinary reasons such as daily transfer limits.",
                        data={"txn_ids": [t.txn_id for t in window], "threshold": threshold},
                    )
                )
                break
    return findings


def find_unusual_amounts(transactions: list[Transaction], exhibit_id: str, factor: float = 5.0, min_history: int = 2) -> list[Finding]:
    findings = []
    history: dict[tuple[str, str], list[float]] = {}
    for txn in transactions:
        key = (txn.from_account, txn.to_account)
        past = history.setdefault(key, [])
        if len(past) >= min_history:
            typical = median(past)
            if typical > 0 and txn.amount >= factor * typical:
                findings.append(
                    Finding(
                        exhibit_id=exhibit_id,
                        analyzer="money",
                        signal="unusual-amount-for-payee",
                        title="Payment far above what this payer usually sends this payee",
                        detail=(
                            f"{txn.txn_id}: {txn.from_account} -> {txn.to_account} {_money(txn.amount)}, "
                            f"{txn.amount / typical:.1f}x the median of {len(past)} earlier payments ({_money(typical)})."
                        ),
                        locator=txn.locator,
                        confidence="medium",
                        limitations="Bulk orders, price changes and annual bills also produce one-off large payments.",
                        data={"median_before": typical, "ratio": round(txn.amount / typical, 2)},
                    )
                )
        past.append(txn.amount)
    return findings


def find_outliers(transactions: list[Transaction], exhibit_id: str, contamination: float = 0.05, seed: int = 7) -> list[Finding]:
    if len(transactions) < 20:
        return []
    out_degree: dict[str, int] = {}
    in_degree: dict[str, int] = {}
    for txn in transactions:
        out_degree[txn.from_account] = out_degree.get(txn.from_account, 0) + 1
        in_degree[txn.to_account] = in_degree.get(txn.to_account, 0) + 1
    features = np.array(
        [
            [
                math.log10(max(t.amount, 1.0)),
                t.timestamp.hour + t.timestamp.minute / 60,
                float(t.timestamp.weekday() >= 5),
                math.log1p(out_degree[t.from_account]),
                math.log1p(in_degree[t.to_account]),
            ]
            for t in transactions
        ]
    )
    model = IsolationForest(contamination=contamination, random_state=seed).fit(features)
    scores = model.decision_function(features)
    labels = model.predict(features)
    findings = []
    for txn, label, score in sorted(zip(transactions, labels, scores), key=lambda item: item[2]):
        if label != -1:
            continue
        findings.append(
            Finding(
                exhibit_id=exhibit_id,
                analyzer="money",
                signal="statistical-outlier",
                title="Statistically unusual transaction",
                detail=f"{txn.as_text()} (isolation score {score:.3f}; lower is more unusual).",
                locator=txn.locator,
                confidence="low",
                limitations="Unusual is not suspicious. This only ranks what to look at first.",
                data={"score": round(float(score), 4)},
            )
        )
    return findings[:5]


def analyze_transactions(path: str | Path, exhibit_id: str, threshold: float = 10_000) -> tuple[list[Transaction], list[Finding]]:
    transactions = load_transactions(path)
    findings = (
        find_round_trips(transactions, exhibit_id)
        + find_pass_through(transactions, exhibit_id)
        + find_structuring(transactions, exhibit_id, threshold=threshold)
        + find_unusual_amounts(transactions, exhibit_id)
        + find_outliers(transactions, exhibit_id)
    )
    return transactions, findings
