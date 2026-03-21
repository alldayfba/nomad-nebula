# Prompt Contracts SOP
> directives/prompt-contracts-sop.md | Version 1.0

---

## Purpose

Prompt contracts are formal specifications for agent interactions — like API contracts but for prompts. They define exact input format, output format, constraints, error handling, and Definition of Done before the agent starts work.

Without contracts, agents improvise output structure. With contracts, output is predictable, validatable, and consistent.

---

## When to Use Contracts

**Required:**
- Client deliverables (emails, ad copy, VSL scripts, audit reports)
- Any output that feeds into another system (CSV → Google Sheets, JSON → webhook)
- Recurring tasks that should produce consistent output

**Optional:**
- Internal brainstorming or research
- One-off exploratory tasks
- Conversations with the user

---

## Contract Format (YAML)

Contracts live in `execution/prompt_contracts/contracts/` as YAML files.

```yaml
name: contract_name              # snake_case identifier
version: "1.0"
description: "What this contract governs"

input:
  required:                       # Fields that MUST be provided
    - field_name: type            # string, number, list, object
      description: "What this field is"
  optional:                       # Fields that may be provided
    - field_name: type
      default: "fallback value"

output:
  format: markdown | json | csv | plaintext
  sections:                       # Required sections in output
    - section_name:
        required: true
        constraints:
          max_chars: 60
          min_words: 10
          pattern: "regex"
  constraints:                    # Global output constraints
    total_words: "150-250"
    tone: "professional_casual"
    no_placeholders: true

definition_of_done:               # ALL must be true for task to be complete
  - "All required sections present"
  - "No placeholder text (e.g., [INSERT], TODO, TBD)"
  - "Constraints validated"

error_handling:
  missing_input: "ask_user | use_default | abort"
  validation_fail: "auto_revise_max_2 | flag_user | abort"
  partial_output: "retry | return_partial_with_warning"
```

---

## Pre-Built Contracts

| Contract | File | Used By |
|---|---|---|
| Cold email | `lead_gen_email.yaml` | outreach bot, email gen SOP |
| Ad script | `ad_script.yaml` | ads-copy bot, asset gen SOP |
| VSL section | `vsl_section.yaml` | content bot, VSL SOP |
| Business audit | `business_audit.yaml` | audit SOP |
| Sourcing report | `sourcing_report.yaml` | sourcing bot |

---

## Execution

### Validating Output Against a Contract

```bash
python execution/prompt_contracts/validate_contract.py \
  --contract execution/prompt_contracts/contracts/lead_gen_email.yaml \
  --output .tmp/generated_email.md
```

Returns:
- `PASS` — all constraints met
- `FAIL` — lists specific violations with line numbers

### Using Contracts in Agent Prompts

Reference the contract in the system prompt or directive:

```markdown
Follow the contract at `execution/prompt_contracts/contracts/lead_gen_email.yaml`.
Validate your output against it before returning.
```

### Programmatic Validation

```python
from execution.prompt_contracts.validate_contract import validate
result = validate("contracts/lead_gen_email.yaml", output_text)
# result = {"pass": True/False, "violations": [...]}
```

---

## Creating New Contracts

1. Identify a recurring output type
2. Copy the template at `execution/prompt_contracts/contracts/_template.yaml`
3. Define input/output/constraints/DoD
4. Test with 3 sample outputs to verify constraints are realistic
5. Reference in the relevant directive

---

## Maintenance

- Contracts version-bumped on breaking changes (input field added/removed, constraint changed)
- Old versions archived, not deleted
- Training Officer can propose contract updates via standard proposal flow
