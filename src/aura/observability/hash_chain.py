"""AURA Cryptographic Hash Chain — tamper-evident audit logging and verification."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

GENESIS_HASH: str = "0" * 64


def canonical_event_repr(event_data: Dict[str, Any], prev_hash: str, sequence_number: int) -> str:
    """Create a canonical deterministic JSON string representation of an audit event for hashing."""
    canonical_payload = {
        "sequence_number": sequence_number,
        "prev_hash": prev_hash,
        "event_id": event_data.get("event_id"),
        "timestamp": str(event_data.get("timestamp")),
        "level": str(event_data.get("level")),
        "event_type": event_data.get("event_type"),
        "session_id": event_data.get("session_id"),
        "run_id": event_data.get("run_id"),
        "request_id": event_data.get("request_id"),
        "assessment_id": event_data.get("assessment_id"),
        "actor": event_data.get("actor"),
        "action": event_data.get("action"),
        "jev": event_data.get("jev"),
        "decision": event_data.get("decision"),
        "execution": event_data.get("execution"),
        "metadata": event_data.get("metadata"),
    }
    return json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_event_hash(event_data: Dict[str, Any], prev_hash: str, sequence_number: int) -> str:
    """Compute the SHA-256 cryptographic hash of an audit event linked to its predecessor."""
    repr_str = canonical_event_repr(event_data, prev_hash, sequence_number)
    return hashlib.sha256(repr_str.encode("utf-8")).hexdigest()


def verify_audit_log_chain(events_file: Path) -> Dict[str, Any]:
    """
    Verify the cryptographic integrity of an AURA audit event log.
    Ensures:
      1. Monotonic sequential numbering without gaps or reordering.
      2. Strict hash chaining: each event's prev_hash matches the prior event's event_hash.
      3. Immutability: each event's recomputed hash matches the recorded event_hash.
    """
    if not events_file.exists():
        return {
            "valid": True,
            "total_events": 0,
            "head_hash": GENESIS_HASH,
            "genesis_hash": GENESIS_HASH,
            "errors": [],
        }

    errors: List[str] = []
    expected_prev = GENESIS_HASH
    expected_seq = 0
    total = 0
    head_hash = GENESIS_HASH

    with open(events_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"Line {line_num}: Corrupted JSON: {e}")
                continue

            total += 1
            seq = data.get("sequence_number")
            prev_hash = data.get("prev_hash")
            event_hash = data.get("event_hash")

            # Verify sequence number
            if seq != expected_seq:
                errors.append(
                    f"Line {line_num} (event_id={data.get('event_id')}): "
                    f"Sequence number gap/mismatch: expected {expected_seq}, got {seq}"
                )

            # Verify prev_hash link
            if prev_hash != expected_prev:
                errors.append(
                    f"Line {line_num} (event_id={data.get('event_id')}): "
                    f"Chain broken: prev_hash mismatch. Expected {expected_prev}, got {prev_hash}"
                )

            # Verify cryptographic hash integrity
            recomputed = compute_event_hash(data, prev_hash or GENESIS_HASH, seq if seq is not None else expected_seq)
            if event_hash != recomputed:
                errors.append(
                    f"Line {line_num} (event_id={data.get('event_id')}): "
                    f"Tamper detected! Recorded hash {event_hash} does not match recomputed {recomputed}"
                )

            expected_prev = event_hash or recomputed
            head_hash = expected_prev
            expected_seq += 1

    return {
        "valid": len(errors) == 0,
        "total_events": total,
        "head_hash": head_hash,
        "genesis_hash": GENESIS_HASH,
        "errors": errors,
    }

