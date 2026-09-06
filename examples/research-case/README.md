# Three-target research example

This workspace contains selected CEACAM5, ITGB6, and FAP records from research
on mucinous colorectal adenocarcinoma. Build the report to compare target
evidence, deposited structures, prepared coordinates, and completed
computational results.

| Target | Included records and outcome |
| --- | --- |
| FAP | Deposited complex [6Y0F](https://www.rcsb.org/structure/6Y0F), a prepared receptor, and Smina/Vinardo docking observations for EGCG with linagliptin and cilengitide controls. EGCG passed the recorded same-protocol score and pose checks. |
| CEACAM5 | Deposited complex [8BW0](https://www.rcsb.org/structure/8BW0), a BoltzGen design, and Boltz2 complex predictions for the design and a shuffled antibody-domain control. The control assessment failed, so no binder candidate was promoted. |
| ITGB6 | Deposited complex [8TCG](https://www.rcsb.org/structure/8TCG) and a derived target preparation. |

Coverage is partial. The docking and binder-design results are computational
hypotheses, and the example contains no experimental validation of them.

The Interventions page includes two source-linked binding-complex references:
linagliptin with FAP in [6Y0F](https://www.rcsb.org/structure/6Y0F), and
tusamitamab Fab with CEACAM5 in [8BW0](https://www.rcsb.org/structure/8BW0).
These deposited structures document binding-site context; they do not establish
efficacy, clinical status, internalization, or tissue selectivity. The exact
entry lookups were reviewed on 2026-09-06.

For a replay that also demonstrates exclusions, unresolved identities, action
comparison, sequence mapping, independent runs, and assay intake, use the
[complete synthetic tutorial](../../docs/tutorial.md).

Validate and build the offline report from the repository root:

```bash
python -m surface_atlas validate examples/research-case
python -m surface_atlas report examples/research-case --output-root ./research-case-report --run-id research-case --json
```

Open `./research-case-report/research-case-example/research-case/index.html`.
The [report guide](../../docs/report.md) explains the structure previews and
how to serve the report locally for interactive viewing.

[artifact-manifest.json](artifact-manifest.json) records the byte count and
SHA-256 digest of each packaged coordinate, sequence, figure, and preview
descriptor. Keep these files with the example when copying it.

## Sources and terms

Target records contain selected Cancer Surfaceome Atlas measurements and
UniProt topology annotations. Compound records cite PubChem, and structure
records cite their RCSB PDB entries. [NOTICE.md](NOTICE.md) identifies these
sources and their terms. Deposited, derived, docked, and predicted files retain
their evidence labels and method names.
