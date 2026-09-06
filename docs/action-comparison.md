# Compare evidence for an action

Open `action-comparison.html` in a generated report. Choose **Payload delivery**,
**Blockade**, or **Imaging**. Each target shows the applicable observations,
their source references, the unknowns, and a proposed next measurement. Follow
the target link to its dossier. Select the targets you want to retain, then
use **Download comparison CSV** or **Copy selected request**. If the browser
cannot write to the clipboard, copy the complete request from the text area.
The selection survives action changes; exports retain the exact target IDs and
current action. Nothing is sent to a service by this page.

The comparison orders targets by the number of supported criteria for the
selected action. Ties use exact target ID. Contradicted and missing criteria
both contribute zero support and remain separately visible; an unknown is
never treated as favorable. Changing action changes which evidence is counted,
not the underlying observations. The page displays previous and current
positions and supported counts when the action changes.

| Action | Three criteria | Proposed experiment class |
| --- | --- | --- |
| Payload delivery | Surface access, internalization, target-dependent payload response | Targeted carrier or conjugate |
| Blockade | Surface access, partner-site access, functional blockade | Site-directed blocking reagent |
| Imaging | Surface access, tissue contrast, tracer retention | Targeted tracer |

These equal-weight counts describe evidence coverage, not target quality,
affinity, safety, efficacy, or therapeutic suitability. A target with more
support can still have an unresolved contradiction. Compare the actual source
contexts before deciding what to measure. Expression, structure tiers, existing
evidence/risk scores, and modality labels do not enter this ordering. The page
does not infer that an assay observation establishes activity in another
context, and it does not independently verify a citation's claims.

## Optional target contract

Existing targets without `action_evidence` remain valid and show three missing
criteria for every action. To add evidence, put this object on its exact target
record in `targets.json`:

```json
{
  "schema_version": "codex-surface-action-evidence/v0.1",
  "target_id": "T-DEMO",
  "sources": [
    {
      "source_id": "S-DEMO",
      "citation": "Synthetic assay fixture, panel A; invented software demonstration."
    }
  ],
  "observations": {
    "surface_access": {
      "state": "supported",
      "basis": "Synthetic intact-cell binding assay in the stated demonstration context.",
      "source_ids": ["S-DEMO"]
    },
    "internalization": {
      "state": "unknown",
      "basis": "No uptake measurement supplied.",
      "source_ids": []
    }
  }
}
```

The nested `target_id` must exactly match the enclosing target. Source IDs must
be unique within the object. Every source needs a citation with enough detail
to identify the original observation, such as the publication or dataset,
figure/table/record, assay context, and relevant limitation. Citations are shown
as text. Observation `basis` should explain the measured context and why it
supports or contradicts that specific criterion. Record conflicts and limited
transferability explicitly; do not relabel expression or a predicted structure
as a measured functional result.

The only observation keys are `surface_access`, `internalization`,
`payload_response`, `partner_site_access`, `functional_blockade`,
`tissue_contrast`, and `tracer_retention`. Each observation requires exactly
`state`, `basis`, and `source_ids`. States are `supported`, `contradicted`, or
`unknown`. Supported and contradicted observations require at least one source
ID resolving within this object. Unknown observations may omit source IDs by
using an empty list. An absent observation is unknown. Extra fields, duplicate
IDs, unresolved references, and target identity mismatches fail validation.
The [JSON Schema](../schemas/v0.1/action-evidence.schema.json) covers object
shape; the Python validator also checks cross-references and exact identity.

## Interpreting the next measurement

The page first proposes revisiting a contradicted criterion, otherwise the
first missing criterion in the action's displayed order. With all three
criteria supported, it proposes replication in the intended context. It states
how a supported, contradicted, or unresolved outcome changes the supported
count. Relative position also depends on the other targets. These are prompts
for experimental planning, not validated assay protocols or authorization to
run an experiment.

For a synthetic ordering demonstration, give target A support for
`surface_access`, `internalization`, and `payload_response`. Give target B
support for `surface_access`, `partner_site_access`, `functional_blockade`,
`tissue_contrast`, and `tracer_retention`. A then leads for payload delivery;
B leads for blockade and imaging. Attach explicit synthetic citations and do
not present these software fixtures as biological measurements.

CSV exports contain one row per selected target and applicable criterion,
including observation state, basis, citations, next measurement, outcome
sensitivity, and the claim caveat. Formula-like cells are prefixed with an
apostrophe for spreadsheet safety. The portable request contains the selected
IDs, action, complete relevant observations, citations, and ordering rule, so
it remains understandable away from the report.
