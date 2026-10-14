# EasySLR account research tool

A small command-line tool that turns researched accounts into CRM-ready CSV rows. Python 3, standard library only.

## Run it

```bash
python3 accounts_tool.py                      # real research -> output/crm_accounts.csv
python3 accounts_tool.py --accounts data/test_accounts.csv --evidence data/test_evidence.csv \
    --overrides data/test_overrides.csv --out output/test_crm_accounts.csv     # test cases
python3 -m unittest discover tests -v         # 11 tests
```

## Inputs

| File | One row is | Key columns |
|---|---|---|
| `data/accounts.csv` | one organisation | `account, domain, hq, human_rank, human_verdict` |
| `data/evidence.csv` | one claim | `account, topic, field, claim, tag, source_url, source_date, checked_by_you` |
| `data/overrides.csv` | one human decision | `account, override_action, reason` |

**Why this shape.** Each claim is its own row with a `tag` of `Verified`, `Interpretation` or `Unknown`, so a fact can never be silently mixed with an opinion. `topic` is a fixed vocabulary (`services, headcount, volume, ai_tooling, buyer, hiring, in_house_tool, competitor, ...`) so rules can ask "is there a verified row for X?" without parsing free text. Overrides live in their own file so re-running the tool never erases a person's decision. `human_rank` and `human_verdict` are passed through untouched: the tool never ranks.

## Output (`output/crm_accounts.csv`)

One row per account. Facts, interpretations and unknowns stay in separate columns (`facts_verified`, `interpretations`, `unknowns`). Also: counts, `source_urls` (Verified claims only), `flags`, `suggested_action` + `suggested_reason`, `override_action` + `override_reason`, `final_action`, `needs_human_review`.

## Rules (first match wins)

1. Verified competing product -> **Exclude**
2. Likely duplicate (same domain, or normalised names >= 0.85 similar) -> **Resolve duplicate**
3. Two Verified headcount or founding-year claims that disagree -> **Resolve conflict**
4. Verified in-house tooling -> **Defer**
5. No Verified need signal (services, hiring, volume) or fewer than 3 Verified facts -> **Research more**
6. Otherwise -> **Discovery call candidate**

Thresholds (`MIN_VERIFIED`, `NAME_MATCH_THRESHOLD`, `CONFLICT_TOLERANCE`) are named constants at the top of the file.

## What is automated and what is not

**Automated (mechanical, cheap to get wrong, easy to check):** tag validation, counting, duplicate flags, missing-field flags (separating "looked and not found" from "never researched"), numeric-conflict flags, stale or source-less Verified claims, the suggested action, CSV export.

**Human review (judgement, or costly if wrong):** choosing the segment; opening each source and setting `checked_by_you`; deciding whether a flagged duplicate is really one company; resolving a conflict; every ranking; interpreting what evidence means for a particular buyer; whether to contact anyone, and what to say. The tool only *suggests*. Any flagged account, any call candidate and any override sets `needs_human_review = Y`. An override needs a reason and is shown next to the original suggestion.

**On the real data, Pharmacoevidence’s own evidence (a published ISPOR poster showing their AI/ML tool used in a NICE UK submission) makes the rule engine suggest “Defer”. I overrode this in data/overrides.csv to “Discovery call candidate” with a written reason, because I still want to test whether they would use an external platform for review types their tool does not cover, or act as a channel for EasySLR.

## Limitation I hit

The tool cannot see meaning, only numbers and strings. While checking Source Health Economics I found it had been sold to SCIRIS (300+ staff), which makes the "small independent firm" reading in an earlier draft doubtful and may move the buying decision up to group level. No rule catches an ownership change: it only surfaced because I searched by hand, and the tool still calls Source a "Discovery call candidate". Likewise `find_conflicts` only compares the first number in a claim, so conflicting *text* (e.g. "Oxford" vs "London and Oxford") is missed.

**With more time:** add an `ownership` check (parent company or acquisition on any Verified row -> flag), compare text conflicts, capture source dates reliably, and push `final_action` straight into a CRM via its API.

## Test cases (`data/test_*.csv`, fictional except one real-name duplicate)

- **Duplicates:** two Northwind rows with the same domain written differently; "Pharmaco Evidence Pvt Ltd" vs the real "Pharmacoevidence" (name only, no domain)
- **Missing evidence:** Harbour Evidence Partners, with a Verified claim that has no URL, plus an Unknown
- **Conflicting information:** Beacon HEOR, 22 vs 150 employees
- **Override:** Quayside Health Economics, suggested as a call candidate, overridden to Defer with a reason
