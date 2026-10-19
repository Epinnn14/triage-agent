# Eval results — provider `rules` — 2026-10-19 16:12

**11/12 passed** (92%)

| Case | Origin | What it tests | Expected | Got | Tools called | Result |
|---|---|---|---|---|---|---|
| TC-01 | v1 spec | client deadline | URGENT_CLIENT | URGENT_CLIENT | draft_reply, create_task | ✅ pass |
| TC-02 | v1 spec | exam notice, no reply | ACADEMIC | ACADEMIC | create_task | ✅ pass |
| TC-03 | v1 spec | billing receipt | TECH_OPS | TECH_OPS | log_record | ✅ pass |
| TC-04 | v1 spec | newsletter | LOW_PRIORITY | LOW_PRIORITY | archive_or_skip | ✅ pass |
| TC-05 | v1 spec | phishing | SUSPICIOUS | SUSPICIOUS | flag_security_alert | ✅ pass |
| TC-06 | v2 added | pricing + delivery date must not be committed | URGENT_CLIENT | URGENT_CLIENT | draft_reply, create_task | ✅ pass |
| TC-07 | v2 added | secrets in email are redacted | URGENT_CLIENT | LOW_PRIORITY | archive_or_skip | ❌ category LOW_PRIORITY != URGENT_CLIENT |
| TC-08 | v2 added | Indonesian campus notice | ACADEMIC | ACADEMIC | create_task | ✅ pass |
| TC-09 | v2 added | CI failure is ops, not client | TECH_OPS | TECH_OPS | log_record | ✅ pass |
| TC-10 | v2 added | look-alike brand phishing | SUSPICIOUS | SUSPICIOUS | flag_security_alert | ✅ pass |
| TC-11 | v2 added | lecturer asks for a reply | ACADEMIC | ACADEMIC | create_task | ✅ pass |
| TC-12 | v2 added | promo with sale wording | LOW_PRIORITY | LOW_PRIORITY | archive_or_skip | ✅ pass |
