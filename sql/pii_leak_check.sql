-- Data-protection control: stored text must never contain raw PII.
-- EXPECTED RESULT: ZERO ROWS. Any row means redaction failed upstream.
-- Same patterns as rqg.guardrails.pii (cards need a Luhn check, done in pii_scan.py).
SELECT
  dt,
  trace_id,
  model,
  CASE
    WHEN regexp_like(coalesce(answer_redacted, '') || ' ' || coalesce(user_input_redacted, ''),
                     '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}') THEN 'email'
    WHEN regexp_like(coalesce(answer_redacted, '') || ' ' || coalesce(user_input_redacted, ''),
                     '(\+91[ -]?)?[6-9][0-9]{4}[ -]?[0-9]{5}') THEN 'phone'
    WHEN regexp_like(coalesce(answer_redacted, '') || ' ' || coalesce(user_input_redacted, ''),
                     'CUST-[0-9]{6}') THEN 'customer_id'
    WHEN regexp_like(coalesce(answer_redacted, '') || ' ' || coalesce(user_input_redacted, ''),
                     'ZH-(AP|KT|SV)-[0-9]{6}') THEN 'serial'
    ELSE 'national_id'
  END AS pii_kind,
  substr(answer_redacted, 1, 60) AS answer_preview
FROM interactions
WHERE dt >= '{{since}}'
  AND regexp_like(
        coalesce(answer_redacted, '') || ' ' || coalesce(user_input_redacted, ''),
        '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|(\+91[ -]?)?[6-9][0-9]{4}[ -]?[0-9]{5}|CUST-[0-9]{6}|ZH-(AP|KT|SV)-[0-9]{6}|[0-9]{4} [0-9]{4} [0-9]{4}'
      )
ORDER BY dt, trace_id;
