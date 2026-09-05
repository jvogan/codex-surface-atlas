# Compute and budget control

When an agent runs external or paid computation, it keeps separate append-only
ledgers for separate billers. Each ledger records ceiling, reserve, settled
spend, unsettled spend, maximum in-flight exposure, remaining capacity, route,
request ID, price source, price timestamp, estimated cost, observed cost,
credits, cash charge, retries, artifact retrieval, and cleanup state. The
local workspace can retain capability and artifact records; the CLI does not
schedule these jobs or maintain provider ledgers.

## Allocate compute

1. Build the complete searched in-scope target census with public evidence and local processing.
2. Give every retained target a Level 0 structure index.
3. Allocate detailed structure work through the selected profile.
4. Select a small set of targets, intended actions, molecule formats, and sites.
5. Run one small technical test per new route.
6. Pilot with positive and negative controls.
7. Expand after controls pass, output files validate, costs fit the budget, and compute cleanup is verified.

## Cost rule

Use the higher of the current list-price calculation and the observed unit cost
from the technical test, then add a 30 percent uncertainty margin. After several
representative runs, use observed p95 cost.

Admit a job only when settled spend, unsettled spend, worst-case in-flight exposure, the next-job upper bound, and the untouched reserve fit inside the ledger ceiling.

Check production pricing before expanding a run. Charge retries to the same
stage budget. Count promotional credits at their USD-equivalent usage.

Use the budget to limit target and candidate counts. Keep the approved model,
checkpoint, precision, construct, sampling depth, seeds, controls, validator,
and required files unchanged. If the work exceeds the budget, reduce counts,
run it in smaller stages, or record a newly approved method and explain how
the change affects the analysis.

## Stop rules

Stop scheduling when any of these conditions occurs:

- projected spend exceeds a ledger ceiling;
- cleanup cannot confirm that unintended compute has stopped;
- target, construct, chain, or residue numbering fails identity checks;
- required artifacts are missing, malformed, unhashed, or inconsistent with receipts;
- positive and negative controls do not separate;
- more than 25 percent of the pilot fails prediction or parsing;
- candidates miss the locked site;
- two consecutive rounds produce no passing candidates;
- diversity collapses into one structural or sequence cluster;
- the route changes model, checkpoint, hardware, precision, or retry behavior without a new preflight;
- private data would cross an undeclared provider boundary.

## Replay

A shareable replay stores durable local artifacts and hashes. Expiring provider URLs are insufficient. The report labels replay, live, evidence-only, unrun, and blocked states.
