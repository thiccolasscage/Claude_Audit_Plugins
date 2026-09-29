# Findings format

Every reviewer returns findings in this shape. In agent or workflow runs, use JSON. In chat, use a table with the same columns.

```json
{
  "verdict": "One or two sentences: is this safe to use or share as is?",
  "findings": [
    {
      "id": "F1",
      "severity": "critical | major | minor | note",
      "lens": "correctness | consistency | privacy | unsupported_claim | instruction_in_data | other",
      "location": "file:line, sheet row/col, slide N, or the quoted claim",
      "evidence": "What the source actually shows. Required; findings without it are dropped.",
      "issue": "What is wrong, in one sentence.",
      "suggested_fix": "Optional.",
      "survived_skeptic": true
    }
  ],
  "not_checked": ["What this review could not verify, and why."]
}
```

## Severity guide

- **critical:** wrong in a way that misleads a decision, exposes personal data, or breaks the thing.
- **major:** wrong or unsupported, likely to be noticed or to matter.
- **minor:** real but low impact.
- **note:** worth knowing, not an error.

Never include personal identifiers in the evidence field. Point to the location and describe the problem instead.
