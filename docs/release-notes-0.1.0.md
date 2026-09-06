# Surface Atlas 0.1.0 alpha

Surface Atlas turns source-linked target records, structures, screens, binder
campaigns, and returned measurements into a portable research report. The local
CLI requires Python 3.10 or later and has no runtime package dependencies.

The [complete offline tutorial](tutorial.md) demonstrates query snapshots,
stable identity reconciliation, duplicate removal, retained/excluded/unresolved
entities, action-dependent comparison, exact sequence/site selection, two
independent campaign runs, failed controls, and a censored assay return.
All tutorial observations and measurements are invented.

Included workflows:

- Compile reviewed local evidence snapshots into a new atlas and reconcile the
  ledger against exact source bytes. Re-importing evidence replaces the managed
  snapshot set in the new output; unreferenced snapshots fail validation.
- Compare recorded support for payload delivery, blockade, and imaging, with
  explicit missing criteria and the next measurement that would change the order.
- Select canonical sequence intervals, map them to exact PDB author residues and
  insertion codes, inspect them in 3D, and export FASTA or a portable request.
- Import independent binder runs with exact constructs, seeds, lineage, controls,
  stages, and promotion decisions; retain failures and work that was not run.
- Import assay returns against exact registered candidate and target constructs,
  preserving endpoint, unit, inequalities, replicates, controls, and missing values.
- Register supplied libraries, merge independent screening runs, install the
  bundled Codex skill, and build offline HTML/JSON/CSV reports with local artifacts.
- Verify exact reviewed inventories for repository exports, source archives, and
  wheels, including packaged resources, wheel RECORD hashes, and generated
  metadata checked against the reviewed project configuration.

The [three-target research example](../examples/research-case/README.md) adds
selected public structural references and computational observations. Its two
known binding-complex records are supported by deposited PDB structures, and its
failed binder control leaves no promoted candidate.

Alpha boundaries: retrieval, model execution, and experiments use separate
plugins or companions. Verified sequence mapping currently requires PDB, although
the general structure viewer also accepts mmCIF. Assay endpoints and units use
an explicit allowlist, with no automatic unit conversion, aggregation, ranking,
or promotion. Legacy binder files receive conservative checks and cannot back
new assay records. Hashes establish file identity; they do not independently
validate the scientific interpretation. No report establishes safety, efficacy,
or clinical suitability.
