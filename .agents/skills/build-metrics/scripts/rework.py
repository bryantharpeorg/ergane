#!/usr/bin/env python3
"""Story rework rate and its trend, read from the live factory stores.

Two definitions are reported because they differ by ~13 points and only one of
them is the honest "had to be redone" number:

  verification rework - the story's first *verified* attempt came back FAIL.
  dispatch rework     - the story was dispatched more than once, for any reason
                        (adds agent_error, timeout, killed, question, which the
                        verification store never sees because nothing was judged).

Both stores are opened read-only. This is production data.

usage: rework.py [repo_path] [--runtime-root DIR]
"""
import collections
import datetime
import os
import re
import sqlite3
import subprocess
import sys
import argparse

WINDOW = 20  # rolling window, in stories


def runtime_root(repo, override=None):
    """Resolve the operator's runtime root without creating it."""
    if override:
        return os.path.join(repo, override) if not os.path.isabs(override) else override
    for name in ("ERGANE_ROOT", "FACTORY_ROOT"):
        if os.environ.get(name):
            value = os.environ[name]
            return value if os.path.isabs(value) else os.path.join(repo, value)
    new = os.path.join(repo, ".ergane")
    legacy = os.path.join(repo, ".factory")
    if os.path.isdir(new):
        return new
    if os.path.isdir(legacy):
        return legacy
    sys.exit(f"missing runtime root: {new} (pass --runtime-root for a temporary store)")


def columns(conn, table):
    return {row[1] for row in conn.execute(f"pragma table_info({table})")}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="rework rate and its trend")
    parser.add_argument("repo", nargs="?", default=".")
    parser.add_argument("--runtime-root")
    return parser.parse_args(argv)


def dispatch_executions(ver):
    available = columns(ver, "verification_results")
    selections = {
        "persona": "persona" if "persona" in available else "NULL",
        "model_alias": "model_alias" if "model_alias" in available else "NULL",
        "route": "route" if "route" in available else "NULL",
        "dispatch": "dispatch" if "dispatch" in available else "NULL",
    }
    rows = ver.execute(
        "select epic_id, node_id, attempt, verdict, "
        f"{selections['persona']}, {selections['model_alias']}, {selections['route']}, "
        f"{selections['dispatch']} "
        "from verification_results "
        "order by epic_id, node_id, 8, 3, 6"
    ).fetchall()
    executions = collections.defaultdict(list)
    for epic, node, attempt, verdict, persona, model, route, dispatch in rows:
        executions[(epic, node, dispatch)].append(
            (
                attempt,
                verdict,
                persona if persona is not None else "unknown",
                model if model is not None else "unknown",
                route if route is not None else "unknown",
            )
        )
    return sorted(executions.items(), key=lambda item: (item[0][0], item[0][1], item[0][2]))


def usage_rows(led):
    available = columns(led, "usage_records")
    tokens = ("prompt_tokens", "completion_tokens", "cache_read_tokens", "cache_write_tokens")
    provenance = ("usage_source", "usage_status", "cost_basis")
    names = (
        "epic_id", "node_id", "attempt", "termination", "issued_at", "key_alias",
        *tokens, "request_count", "spend_usd", *provenance,
    )
    selections = []
    for name in names:
        if name in provenance:
            default = "legacy" if name != "cost_basis" else "unknown"
            selections.append(name if name in available else f"'{default}'")
        elif name in tokens or name in ("request_count", "spend_usd"):
            selections.append(name if name in available else "NULL")
        else:
            selections.append(name)
    return [dict(zip(names, row)) for row in led.execute(f"select {', '.join(selections)} from usage_records")]


def quantity(label, values, total):
    measured = sum(values) if values else "unknown"
    suffix = f" ({len(values)}/{total} measured)" if total else " (no rows)"
    return f"  {label} measured {measured}{suffix}"


def print_usage_metrics(led):
    rule("USAGE MEASUREMENTS")
    rows = usage_rows(led)
    print(f"  usage rows {len(rows)}")
    if not rows:
        print("  no ledger rows")
        return
    print(quantity("prompt tokens", [row["prompt_tokens"] for row in rows if row["prompt_tokens"] is not None], len(rows)))
    print(quantity("completion tokens", [row["completion_tokens"] for row in rows if row["completion_tokens"] is not None], len(rows)))
    print(quantity("cache-read tokens", [row["cache_read_tokens"] for row in rows if row["cache_read_tokens"] is not None], len(rows)))
    print(quantity("cache-write tokens", [row["cache_write_tokens"] for row in rows if row["cache_write_tokens"] is not None], len(rows)))
    print(quantity("requests", [row["request_count"] for row in rows if row["request_count"] is not None], len(rows)))
    print(quantity("dollars", [row["spend_usd"] for row in rows if row["spend_usd"] is not None], len(rows)))
    unmeasured = sum(value is None for row in rows for value in (
        row["prompt_tokens"], row["completion_tokens"], row["cache_read_tokens"],
        row["cache_write_tokens"], row["request_count"], row["spend_usd"],
    ))
    print(f"  unmeasured quantities  {unmeasured}")
    rule("ACCOUNTING PROVENANCE")
    runner_unknown = sum(row["usage_source"] in ("legacy", "") for row in rows)
    print(f"  runner unknown {runner_unknown}")
    print(f"  usage sources          {' '.join(sorted({row['usage_source'] for row in rows}))}")
    print(f"  usage statuses         {' '.join(sorted({row['usage_status'] for row in rows}))}")
    print(f"  cost bases             {' '.join(sorted({row['cost_basis'] for row in rows}))}")


def print_dispatches(ver):
    rule("DISPATCH EXECUTIONS")
    executions = dispatch_executions(ver)
    if not executions:
        print("  no verification results")
        return
    for (epic, node, dispatch), attempts in executions:
        print(f"  {epic}/{node} dispatch {dispatch}")
        for attempt, verdict, persona, model, route in attempts:
            print(f"    attempt {attempt} {verdict} persona={persona} model={model} route={route}")


def monday(day):
    d = datetime.date.fromisoformat(day)
    return (d - datetime.timedelta(days=d.weekday())).isoformat()


def ro(path):
    if not os.path.exists(path):
        sys.exit(f"missing store: {path} (run from the repo root, or pass its path)")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def rule(title):
    print(f"\n=== {title} ===")


def main(repo):
    os.chdir(repo)
    parsed = parse_args()
    repo = parsed.repo
    root = runtime_root(parsed.repo, parsed.runtime_root)
    ver = ro(os.path.join(root, "verification.db"))
    led = ro(os.path.join(root, "ledger.db"))

    # ---- verification level -------------------------------------------------
    verification_columns = columns(ver, "verification_results")
    rows = ver.execute(
        "select epic_id, node_id, attempt, verdict, finished_at, form, "
        f"{'dispatch' if 'dispatch' in verification_columns else 'NULL'} "
        "from verification_results order by finished_at"
    ).fetchall()
    if not rows:
        rule("VERIFICATION-LEVEL REWORK (first verified attempt came back FAIL)")
        print("  verification rows 0")
        print("  no verification results")

    forms = {r[5] for r in rows}
    attempts = collections.defaultdict(dict)
    for epic, node, att, verdict, fin, _form, dispatch in rows:
        # keep the worst verdict if a story somehow has both forms at one attempt
        prev = attempts[(epic, node, dispatch)].get(att)
        if prev is None or (prev["v"] == "PASS" and verdict == "FAIL"):
            attempts[(epic, node, dispatch)][att] = {"v": verdict, "f": fin}

    stories = []
    for key, att in attempts.items():
        lo = min(att)  # not hardcoded to 1: restored stores can lose attempt 1
        passed_at = min((a for a, x in att.items() if x["v"] == "PASS"), default=None)
        stories.append(
            {
                "key": key,
                "day": att[lo]["f"][:10],
                "ts": att[lo]["f"],
                "reworked": att[lo]["v"] == "FAIL",
                "passed_at": passed_at,
                "n": len(att),
            }
        )
    stories.sort(key=lambda s: s["ts"])
    n = len(stories)
    rw = sum(s["reworked"] for s in stories)

    if rows:
        print(f"window: {rows[0][4][:10]} -> {rows[-1][4][:10]}   forms present: {sorted(forms)}")
        rule("VERIFICATION-LEVEL REWORK (first verified attempt came back FAIL)")
        print(f"  stories verified   {n}")
        print(f"  passed first try   {n - rw}  ({100 * (n - rw) / n:.1f}%)")
        print(f"  REWORKED           {rw}  ({100 * rw / n:.1f}%)")

        depth = collections.Counter(
            s["passed_at"] if s["passed_at"] is not None else "never" for s in stories
        )
        print("\n  landed on:")
        for k in sorted(depth, key=lambda x: (x == "never", x)):
            label = "never passed" if k == "never" else f"attempt {k}"
            print(f"    {label:<14}{depth[k]:>4}  ({100 * depth[k] / n:>5.1f}%)")

    print_dispatches(ver)

    # ---- dispatch level -----------------------------------------------------
    urows = led.execute(
        "select epic_id, node_id, attempt, termination, issued_at from usage_records"
    ).fetchall()
    disp = collections.defaultdict(set)
    firstseen = {}
    term = collections.Counter()
    for epic, node, att, t, iss in urows:
        k = (epic, node)
        disp[k].add(att)
        term[t] += 1
        if k not in firstseen or iss < firstseen[k]:
            firstseen[k] = iss
    dn = len(disp)
    drw = sum(1 for v in disp.values() if len(v) > 1)

    rule("DISPATCH-LEVEL REWORK (dispatched more than once, for any reason)")
    print(f"  stories dispatched {dn}")
    if dn:
        print(f"  REWORKED           {drw}  ({100 * drw / dn:.1f}%)   <- lead with this one")
        print(f"  mean attempts/story {sum(len(v) for v in disp.values()) / dn:.2f}")
    else:
        print("  REWORKED           0  (no ledger stories)")
    if dn:
        print("\n  attempts dispatched per story:")
        for k, c in sorted(collections.Counter(len(v) for v in disp.values()).items()):
            print(f"    {k} attempt(s)  {c:>4}  ({100 * c / dn:>5.1f}%)")
    if urows:
        print("\n  terminations (rows, ~2 per attempt - one per persona):")
        for k, c in term.most_common():
            print(f"    {k:<14}{c:>5}  ({100 * c / len(urows):>5.1f}%)")
    else:
        print("  no terminations")

    print_usage_metrics(led)

    # ---- trend --------------------------------------------------------------
    rule("TREND BY WEEK (stories dated by their first attempt)")
    byweek = collections.defaultdict(lambda: [0, 0, 0, 0])  # vN, vRework, dN, dRework
    for s in stories:
        b = byweek[monday(s["day"])]
        b[0] += 1
        b[1] += s["reworked"]
    for k, v in disp.items():
        b = byweek[monday(firstseen[k][:10])]
        b[2] += 1
        b[3] += len(v) > 1
    print(f"  {'week of':<13}{'stories':>8}{'verif rework':>15}{'dispatch rework':>18}")
    for w in sorted(byweek):
        vn, vr, dnw, dr = byweek[w]
        vs = f"{vr}/{vn} ({100 * vr / vn:.1f}%)" if vn else "-"
        ds = f"{dr}/{dnw} ({100 * dr / dnw:.1f}%)" if dnw else "-"
        print(f"  {w:<13}{vn:>8}{vs:>15}{ds:>18}")

    rule(f"ROLLING {WINDOW}-STORY WINDOW (chronological; fixed denominator)")
    if n >= WINDOW:
        for i in range(0, n - WINDOW + 1, 5):
            win = stories[i : i + WINDOW]
            r = sum(s["reworked"] for s in win)
            bar = "#" * round(r / WINDOW * 40)
            print(
                f"  {i + 1:>3}-{i + WINDOW:<4}{win[0]['day']} -> {win[-1]['day']}"
                f"  {100 * r / WINDOW:>5.1f}% {bar}"
            )
        win = stories[-WINDOW:]
        r = sum(s["reworked"] for s in win)
        print(f"  LAST {WINDOW}   {win[0]['day']} -> {win[-1]['day']}  {100 * r / WINDOW:>5.1f}%")
    else:
        print(f"  only {n} stories; need {WINDOW}")

    # ---- coverage -----------------------------------------------------------
    rule("COVERAGE (state this in the report - the stores are not a census)")
    subj = subprocess.run(
        ["git", "log", "--no-merges", "--format=%s"], capture_output=True, text=True
    ).stdout.splitlines()
    node_re = re.compile(r"^(\d{3}-[a-z0-9-]+)/(us\d+)")
    landed = {f"{m.group(1)}/{m.group(2)}" for s in subj if (m := node_re.match(s))}
    have = {f"{e}/{nd}" for e, nd in disp}
    missing = sorted(landed - have)
    never = sorted(have - landed)
    print(f"  story landings in git   {len(landed)}")
    print(f"  stories in the ledger   {len(have)}")
    measured = len(landed & have)
    cov = f"{100 * measured / len(landed):.0f}%" if landed else "unknown"
    print(f"  landed AND measured     {len(landed & have)}  ({cov} coverage)")
    print(f"\n  landed but NOT in the ledger ({len(missing)}) - lost store data:")
    for s in missing[:12]:
        print(f"    {s}")
    if len(missing) > 12:
        print(f"    ... and {len(missing) - 12} more")
    print(f"\n  in the ledger but never landed ({len(never)}) - killed or in flight:")
    for s in never[:12]:
        print(f"    {s}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
