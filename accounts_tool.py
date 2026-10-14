#!/usr/bin/env python3
"""Turn account research (accounts + tagged evidence) into CRM-ready CSV rows.

Inputs (CSV):
  accounts.csv   one row per organisation: account, domain, hq, human_rank, human_verdict
  evidence.csv   one row per claim: account, topic, field, claim, tag, source_url, source_date, checked_by_you
  overrides.csv  optional, a person's decisions: account, override_action, reason

What it does:
  1. Validates tags (Verified / Interpretation / Unknown).
  2. Flags likely duplicate accounts (similar name OR same domain).
  3. Flags missing information, and conflicting verified claims.
  4. Suggests a next action with simple rules, then applies any human override.
  5. Writes one CSV row per account, keeping facts, interpretations and unknowns apart.

Standard library only.
"""
import argparse
import csv
import re
import sys
from datetime import date
from difflib import SequenceMatcher

# ---------------------------------------------------------------- settings
TAGS = ("Verified", "Interpretation", "Unknown")

# Topics every account should have at least one Verified row for.
REQUIRED_TOPICS = ["services", "headcount", "volume", "ai_tooling", "buyer"]

# Verified evidence on any of these counts as a signal of SLR need.
NEED_TOPICS = {"services", "hiring", "volume"}

# Topics where two Verified claims with different numbers count as a conflict,
# and how far apart (as a fraction) they may be before we call it a conflict.
CONFLICT_TOLERANCE = {"headcount": 0.20, "founded": 0.0}

# Actions in priority order: the first rule that matches wins.
ACTIONS = [
    "Exclude",
    "Resolve duplicate",
    "Resolve conflict",
    "Defer",
    "Research more",
    "Discovery call candidate",
]

# Words ignored when comparing organisation names.
NAME_NOISE = {"pvt", "ltd", "limited", "inc", "llc", "llp", "plc", "corp",
              "co", "company", "group", "the"}
NAME_MATCH_THRESHOLD = 0.85   # 0..1, higher = stricter
STALE_AFTER_YEARS = 2         # a dated source older than this is flagged
MIN_VERIFIED = 3              # fewer Verified facts than this -> "Research more"


# ---------------------------------------------------------------- loading
def read_csv(path, required_cols, optional=False):
    """Read a CSV into a list of dicts and check the columns exist."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            cols = set(reader.fieldnames or [])
            rows = list(reader)
    except FileNotFoundError:
        if optional:
            return []
        sys.exit(f"ERROR: file not found: {path}")
    missing = set(required_cols) - cols
    if missing:
        sys.exit(f"ERROR: {path} is missing columns: {sorted(missing)}")
    for r in rows:  # strip stray whitespace everywhere
        for k, v in r.items():
            r[k] = (v or "").strip()
    return rows


def check_tags(evidence):
    """Stop on any row whose tag is not one of the three allowed values."""
    bad = [(i + 2, r["account"], r["tag"]) for i, r in enumerate(evidence)
           if r["tag"] not in TAGS]
    if bad:
        for line, acct, tag in bad:
            print(f"ERROR: evidence line {line} ({acct}): tag '{tag}' not in {TAGS}",
                  file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------- duplicates
def normalise_name(name):
    """'Pharmaco-Evidence Pvt. Ltd.' -> 'pharmacoevidence'."""
    words = re.findall(r"[a-z0-9]+", name.lower())
    return "".join(w for w in words if w not in NAME_NOISE)


def normalise_domain(domain):
    """'https://www.IconPLC.com/x' -> 'iconplc.com'."""
    d = domain.lower().strip()
    d = re.sub(r"^https?://", "", d)
    d = re.sub(r"^www\.", "", d)
    return d.split("/")[0]


def find_duplicates(accounts):
    """Return {account: ['other account (reason)', ...]} for likely duplicates."""
    dupes = {a["account"]: [] for a in accounts}
    for i, a in enumerate(accounts):
        for b in accounts[i + 1:]:
            reasons = []
            da, db = normalise_domain(a["domain"]), normalise_domain(b["domain"])
            if da and da == db:
                reasons.append(f"same domain {da}")
            score = SequenceMatcher(None, normalise_name(a["account"]),
                                    normalise_name(b["account"])).ratio()
            if score >= NAME_MATCH_THRESHOLD:
                reasons.append(f"similar name ({score:.2f})")
            if reasons:
                dupes[a["account"]].append(f"{b['account']} ({', '.join(reasons)})")
                dupes[b["account"]].append(f"{a['account']} ({', '.join(reasons)})")
    return dupes


# ---------------------------------------------------------------- evidence checks
def first_number(text):
    """First whole number in a claim, ignoring thousands commas ('1,200' -> 1200)."""
    m = re.search(r"\d[\d,]*", text)
    return int(m.group().replace(",", "")) if m else None


def find_conflicts(rows):
    """Two Verified rows on the same topic with clearly different numbers."""
    conflicts = []
    for topic, tol in CONFLICT_TOLERANCE.items():
        vals = [(first_number(r["claim"]), r) for r in rows
                if r["topic"] == topic and r["tag"] == "Verified"]
        vals = [(n, r) for n, r in vals if n is not None]
        for i, (n1, r1) in enumerate(vals):
            for n2, r2 in vals[i + 1:]:
                if abs(n1 - n2) > tol * max(n1, n2):
                    conflicts.append(f"{topic}: {n1} vs {n2}")
    return conflicts


def is_weak_source(row):
    """Verified claim with no real URL (blank, 'Not found', or analyst note)."""
    url = row["source_url"].lower()
    return not url.startswith("http")


def is_stale(row):
    """Source marked expired, or dated more than STALE_AFTER_YEARS ago."""
    d = row["source_date"].lower()
    if "expired" in d:
        return True
    m = re.search(r"(19|20)\d\d", d)
    return bool(m) and int(m.group()) < date.today().year - STALE_AFTER_YEARS


# ---------------------------------------------------------------- per-account analysis
def analyse(account, rows, dupes):
    """Build the full record for one account."""
    by_tag = {t: [r for r in rows if r["tag"] == t] for t in TAGS}
    verified_topics = {r["topic"] for r in by_tag["Verified"]}
    unknown_topics = {r["topic"] for r in by_tag["Unknown"]}

    flags = []
    # Missing info: separate gaps we looked for (Unknown row) from gaps nobody looked at.
    missing = [t for t in REQUIRED_TOPICS if t not in verified_topics]
    for t in missing:
        kind = "unknown (looked, not found)" if t in unknown_topics else "not researched"
        flags.append(f"missing {t}: {kind}")
    if not normalise_domain(account["domain"]):
        flags.append("missing domain (duplicate check is name-only)")

    weak = [r for r in by_tag["Verified"] if is_weak_source(r)]
    if weak:
        flags.append(f"{len(weak)} Verified claim(s) without a source URL")
    stale = [r for r in by_tag["Verified"] if is_stale(r)]
    if stale:
        flags.append(f"{len(stale)} Verified claim(s) from an expired or old source")

    conflicts = find_conflicts(rows)
    for c in conflicts:
        flags.append(f"conflicting verified claims, {c}")
    if dupes:
        flags.append("possible duplicate of " + "; ".join(dupes))

    # Next-action rules (first match wins).
    competitor = any(r["topic"] == "competitor" for r in by_tag["Verified"])
    in_house = "in_house_tool" in verified_topics
    has_need = bool(NEED_TOPICS & verified_topics)
    if competitor:
        action, why = "Exclude", "Verified evidence that they sell a competing product"
    elif dupes:
        action, why = "Resolve duplicate", "Merge or confirm separate before any outreach"
    elif conflicts:
        action, why = "Resolve conflict", "Verified claims disagree; check the sources"
    elif in_house:
        action, why = "Defer", "Verified in-house tooling makes buying a platform harder"
    elif not has_need or len(by_tag["Verified"]) < MIN_VERIFIED:
        action, why = "Research more", f"Fewer than {MIN_VERIFIED} Verified facts or no verified SLR-need signal"
    else:
        action, why = "Discovery call candidate", "Verified need signal and no blocking flags"

    return {
        "account": account["account"],
        "domain": normalise_domain(account["domain"]),
        "hq": account["hq"],
        "human_rank": account["human_rank"],
        "human_verdict": account["human_verdict"],
        "verified_count": len(by_tag["Verified"]),
        "interpretation_count": len(by_tag["Interpretation"]),
        "unknown_count": len(by_tag["Unknown"]),
        "verified_unchecked": sum(1 for r in by_tag["Verified"]
                                  if r["checked_by_you"].upper() != "Y"),
        "facts_verified": " | ".join(f"{r['field']}: {r['claim']}" for r in by_tag["Verified"]),
        "interpretations": " | ".join(f"{r['field']}: {r['claim']}" for r in by_tag["Interpretation"]),
        "unknowns": " | ".join(f"{r['field']}: {r['claim']}" for r in by_tag["Unknown"]),
        "source_urls": " | ".join(sorted({r["source_url"] for r in by_tag["Verified"]
                                          if r["source_url"].startswith("http")})),
        "flags": "; ".join(flags),
        "suggested_action": action,
        "suggested_reason": why,
        "_has_flags": bool(flags),
    }


# ---------------------------------------------------------------- overrides + output
def apply_overrides(records, overrides):
    """A person's override wins over the rule. Unknown actions are rejected."""
    by_account = {o["account"]: o for o in overrides}
    names = {r["account"] for r in records}
    for o in overrides:
        if o["account"] not in names:
            sys.exit(f"ERROR: override for unknown account '{o['account']}'")
        if o["override_action"] not in ACTIONS:
            sys.exit(f"ERROR: override action '{o['override_action']}' not in {ACTIONS}")
        if not o["reason"]:
            sys.exit(f"ERROR: override for '{o['account']}' needs a reason")
    for r in records:
        o = by_account.get(r["account"])
        r["override_action"] = o["override_action"] if o else ""
        r["override_reason"] = o["reason"] if o else ""
        r["final_action"] = r["override_action"] or r["suggested_action"]
        # A person must look at anything flagged, any call candidate, and any override.
        r["needs_human_review"] = "Y" if (
            r.pop("_has_flags") or r["final_action"] == "Discovery call candidate"
            or r["override_action"]) else "N"


COLUMNS = ["account", "domain", "hq", "human_rank", "human_verdict",
           "verified_count", "interpretation_count", "unknown_count", "verified_unchecked",
           "facts_verified", "interpretations", "unknowns", "source_urls",
           "flags", "suggested_action", "suggested_reason",
           "override_action", "override_reason", "final_action", "needs_human_review"]


def run(accounts_path, evidence_path, overrides_path, out_path):
    accounts = read_csv(accounts_path, ["account", "domain", "hq", "human_rank", "human_verdict"])
    evidence = read_csv(evidence_path, ["account", "topic", "field", "claim", "tag",
                                        "source_url", "source_date", "checked_by_you"])
    overrides = read_csv(overrides_path, ["account", "override_action", "reason"], optional=True)
    check_tags(evidence)

    names = {a["account"] for a in accounts}
    for r in evidence:
        if r["account"] not in names:
            print(f"WARNING: evidence for '{r['account']}' has no matching account row",
                  file=sys.stderr)

    dupes = find_duplicates(accounts)
    records = [analyse(a, [r for r in evidence if r["account"] == a["account"]],
                       dupes[a["account"]]) for a in accounts]
    apply_overrides(records, overrides)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(records)
    return records


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--accounts", default="data/accounts.csv")
    p.add_argument("--evidence", default="data/evidence.csv")
    p.add_argument("--overrides", default="data/overrides.csv")
    p.add_argument("--out", default="output/crm_accounts.csv")
    args = p.parse_args()

    records = run(args.accounts, args.evidence, args.overrides, args.out)
    print(f"Wrote {len(records)} accounts to {args.out}\n")
    for r in records:
        mark = f" (override: {r['override_action']})" if r["override_action"] else ""
        print(f"{r['account']:<28} V{r['verified_count']} I{r['interpretation_count']} "
              f"U{r['unknown_count']}  -> {r['final_action']}{mark}"
              f"  [review: {r['needs_human_review']}]")


if __name__ == "__main__":
    main()
