# Lab templates

Concrete files lab members fill in. Rules behind each: design/decisions.md in ~/gitrepos/research-lab-pilot. A lab is one flat
directory (see SKILL.md section 1).

| Template | Filled by | When | Lives in |
|---|---|---|---|
| `experiment.md` | brief: overseer (or worker for designs); entry: worker | per experiment | lab `experiments/<id>.md` |
| `manifest.md` | worker | with the entry | lab `experiments/<id>_manifest.py` |
| `critic-design-review.md` | owner launches; critic fills verdict | headline briefs, before dispatch | lab `audit/` |
| `critic-result-audit.md` | owner launches; critic fills verdict | after the entry | lab `audit/` |
| `critic-page-audit.md` | author launches; critic fills verdict | before a page publish | lab `audit/` |
| `policy.md` | PI with overseer | lab startup | lab `policy.md` |
| `questions.md` | overseer | lab startup, then ongoing | lab `questions.md` |
| `audit-log.md` | whoever closes a gate | per gate outcome | lab `audit/log.md` |

Flow for one experiment:

```
questions.md row --> experiment.md (Brief) --[headline]--> critic-design-review
   --> run --> experiment.md (Entry) + manifest --> run_checks + coverage_scan (deterministic)
   --> critic-result-audit (+ attack-claims on claims) --> decision (status set in manifest)
   --> page --> critic-page-audit --> publish; every gate outcome -> audit/log.md
```
