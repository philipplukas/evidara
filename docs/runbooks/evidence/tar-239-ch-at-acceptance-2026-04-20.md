=== TAR-239 CH+AT Acceptance Evidence (2026-04-20) ===

### CH Fedlex Compliance Policy
- Policy ID: cp_ch_fedlex_open_data
- Robots mode: ignore
- Rate corridor: 30–60–600 rpm
- Concurrent: 4
- Attribution: True — "Source: Fedlex — Swiss Federal Chancellery (open-data programme)."
- Contact: https://evidara.ai/contact

### AT RIS Compliance Policy
- Policy ID: cp_at_ris_ogd
- Robots mode: ignore
- Rate corridor: 30–60–600 rpm
- Attribution: True — "Source: Rechtsinformationssystem des Bundes (RIS), Bundeskanzleramt Österreich — Open Government Data."

### CH Jurisdiction + Federal Scope
- CH jurisdictions: 28 (federal + 26 cantons + country)
  - jur_ch: Switzerland
  - jur_ch_ag: Kanton Aargau
  - jur_ch_ai: Kanton Appenzell Innerrhoden
  - jur_ch_ar: Kanton Appenzell Ausserrhoden
  - jur_ch_be: Kanton Bern / Canton de Berne
  ... and 23 more
- AT jurisdictions: 1
  - jur_at: Austria

### CH Authorities
- CH authorities: 12
  - auth_be_sk: Staatskanzlei Kanton Bern / Chancellerie d'État du canton de Berne
  - auth_bger: Bundesgericht
  - auth_bpger: Bundespatentgericht / Tribunal fédéral des brevets
  - auth_bs_sk: Staatskanzlei Basel-Stadt
  - auth_bstger: Bundesstrafgericht / Tribunal pénal fédéral
  ... and 7 more
- AT authorities: 4
  - auth_at_ogh: Oberster Gerichtshof
  - auth_at_ris: Rechtsinformationssystem des Bundes
  - auth_at_vfgh: Verfassungsgerichtshof
  - auth_at_vwgh: Verwaltungsgerichtshof

### Assessment
CH and AT reference data, compliance policies, and jurisdiction hierarchies are fully operational on prod.
The compliance plane (rate limiting, robots mode, attribution) is activated for both countries.
