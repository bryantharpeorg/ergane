"""Read-only historical recovery preview. Never writes or migrates a ledger.

The daily export must include one-to-one alias/key mapping evidence from retained
request logs. Missing mappings remain unresolved, even when costs look similar.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from factory.usage.cli import open_readonly


def preview(db: Path, daily: list[dict[str, Any]]) -> dict[str, Any]:
    candidates = []
    unresolved = []
    indexed: dict[str, list[dict[str, Any]]] = {}
    for item in daily:
        indexed.setdefault(item['key_alias'], []).append(item)
    with open_readonly(db) as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute('SELECT * FROM usage_records ORDER BY id'):
            alias = row['key_alias']
            matches = indexed.get(alias, [])
            reason = None
            if len(matches) != 1:
                reason = 'missing_or_ambiguous_key_mapping'
            else:
                source = matches[0]
                if source.get('mapping_key_count') != 1 or source.get('mapping_alias_count') != 1:
                    reason = 'ambiguous_key_mapping'
                elif not _inside_attempt(row, source):
                    reason = 'request_evidence_outside_attempt'
                elif not all(isinstance(source.get(k), int) and not isinstance(source[k], bool) and source[k] >= 0 for k in ('prompt_tokens','completion_tokens','request_count')):
                    reason = 'unusable_counters'
                elif row['spend_usd'] is None or isinstance(source.get('spend_usd'), bool) or not isinstance(source.get('spend_usd'), (float,int)) or not math.isclose(row['spend_usd'], source['spend_usd'], rel_tol=1e-6, abs_tol=1e-8):
                    reason = 'cost_does_not_reconcile'
            if reason is not None:
                unresolved.append({'key_alias':alias,'reason':reason})
                continue
            fields = ('prompt_tokens','completion_tokens','request_count')
            before = {field:row[field] for field in fields}
            after = {field:source[field] for field in fields}
            if before != after:
                candidates.append({'key_alias':alias,'source':'litellm_daily','before':before,'proposed':after,
                                   'spend_usd':row['spend_usd'],'mapping_evidence':{
                                       'first_request_at':source['first_request_at'],'last_request_at':source['last_request_at']}})
    return {'dry_run':True,'candidate_count':len(candidates),'unresolved_count':len(unresolved),
            'candidates':candidates,'unresolved':unresolved}


def _inside_attempt(row: sqlite3.Row, source: dict[str, Any]) -> bool:
    try:
        values = [datetime.fromisoformat(value.replace('Z', '+00:00')) for value in (
            row['issued_at'], source['first_request_at'], source['last_request_at'], row['torn_down_at'],
        )]
        return all(value.tzinfo is not None for value in values) and values == sorted(values)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,required=True)
    parser.add_argument('--daily-totals',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(preview(args.db,json.loads(args.daily_totals.read_text())),indent=2))


if __name__ == '__main__':
    main()
