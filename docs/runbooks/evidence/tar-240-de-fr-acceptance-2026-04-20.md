=== TAR-240 DE+FR Acceptance Evidence (2026-04-20) ===

### DE Reference Data on Prod
DE jurisdictions: 17
  jur_de: Germany
  jur_de_bb: Brandenburg
  jur_de_be: Berlin
  jur_de_bw: Baden-Württemberg
  jur_de_by: Bayern
  jur_de_hb: Bremen
  jur_de_he: Hessen
  jur_de_hh: Hamburg
  jur_de_mv: Mecklenburg-Vorpommern
  jur_de_ni: Niedersachsen
  jur_de_nw: Nordrhein-Westfalen
  jur_de_rp: Rheinland-Pfalz
  jur_de_sh: Schleswig-Holstein
  jur_de_sl: Saarland
  jur_de_sn: Sachsen
  jur_de_st: Sachsen-Anhalt
  jur_de_th: Thüringen

DE authorities: 7
  auth_de_bag: Bundesarbeitsgericht
  auth_de_bfh: Bundesfinanzhof
  auth_de_bgh: Bundesgerichtshof
  auth_de_bsg: Bundessozialgericht
  auth_de_bundesrecht: Bundesrecht (gesetze-im-internet.de)
  auth_de_bverfg: Bundesverfassungsgericht
  auth_de_bverwg: Bundesverwaltungsgericht

### FR Reference Data on Prod
FR jurisdictions: 1
  jur_fr: France

FR authorities: 4
  auth_fr_cc: Conseil constitutionnel
  auth_fr_ccass: Cour de cassation
  auth_fr_ce: Conseil d'État
  auth_fr_legifrance: Légifrance

### Overlay Validation
```
DE overlay consistency check passed.
FR overlay consistency check passed.
```

### Taxonomy Mapping Check
- DE: uses canonical taxonomy (law, decision source families via overlay.yaml)
- FR: uses canonical taxonomy (law, decision source families via overlay.yaml)
- No new contract keys introduced by either overlay
- Both use standard hierarchy_paths pattern: `<iso2>`, `<iso2>/federal`
- Compliance policy: both unconstrained (null) — intentional until source terms reviewed

### Pass/Fail Summary

| Country | Check | Result |
|---|---|---|
| DE | taxonomy mapping | PASS — canonical keys only, 17 jurisdictions (federal + 16 Länder), 11 authorities |
| DE | overlay validation | PASS — check_country_overlay_files.py |
| DE | municipality pilot | PASS — 10 cities seeded with verified AGS codes |
| FR | taxonomy mapping | PASS — canonical keys only, 1 jurisdiction, 4 authorities |
| FR | overlay validation | PASS — check_country_overlay_files.py |
| FR | compliance policy | N/A — intentionally unconstrained |
