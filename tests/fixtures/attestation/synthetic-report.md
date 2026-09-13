# Attestation: org/repo:167/US3

- launch `builder-1`: outcome `failed`
- launch `builder-2`: outcome `succeeded`

## Judge history

- `eval-1` status `parse_error`: failed
  - `US3-S1`: `fail` — covered
- `eval-2` status `valid`: passed
  - `US3-S1`: `pass` — covered

## Verification

- attempt 1: `PASS`
- attempt 2: `PASS`

## Completeness

- `test|coverage.txt|dispatch-2|capture-2`: `included` — retained declared artifact

## Usage

- {&#x27;builder_or_judge&#x27;: &#x27;builder&#x27;, &#x27;usage_source&#x27;: &#x27;gateway&#x27;, &#x27;usage_status&#x27;: &#x27;partial&#x27;, &#x27;cost_basis&#x27;: &#x27;gateway_usd&#x27;, &#x27;complete_total&#x27;: None}
- {&#x27;builder_or_judge&#x27;: &#x27;builder&#x27;, &#x27;usage_source&#x27;: &#x27;gateway&#x27;, &#x27;usage_status&#x27;: &#x27;complete&#x27;, &#x27;cost_basis&#x27;: &#x27;gateway_usd&#x27;, &#x27;complete_total&#x27;: 0.01}

Attachments are exact retained bytes. Opaque bytes are not redacted and may contain sensitive data.
