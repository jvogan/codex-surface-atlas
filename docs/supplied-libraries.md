# Supplied libraries

Register an SDF, SMILES, CSV, or FASTA library before using it in an atlas.
Registration copies the supplied files into a new local directory and writes
their identities, sequences where present, and checksums to a molecular-library
collection. It does not predict a target relationship or create a screening
result.

Try the [runnable example](../examples/supplied-library/README.md) with two
compound records and a synthetic peptide, or prepare your own manifest below.

## Create a registration manifest

Save this CSV manifest as
`library-registration.json` beside `compounds.csv`:

```json
{
  "schema_version": "surface-atlas-supplied-library-registration/v1",
  "atlas_id": "library-study",
  "library_id": "supplied-library",
  "inputs": [
    {
      "input_library_id": "compounds",
      "format": "csv",
      "molecular_class": "small-molecule",
      "path": "compounds.csv",
      "smiles_column": "smiles",
      "id_column": "id",
      "name_column": "name"
    }
  ]
}
```

The [full template](../skills/codex-surface-targets/assets/supplied-library-registration.template.json)
also includes SDF, SMILES, and FASTA inputs. Keep the entries for your files and
replace their placeholders.

Each input path is relative to the manifest unless it is absolute. SDF entries
preserve source records. A SMILES line contains the SMILES string, an optional
record ID, and an optional name. CSV entries specify the SMILES, ID, and name
columns. FASTA entries can name a JSON sidecar for modifications or construct
details. Set `atlas_id` to `library-study` for the example below.

## Register the files

Choose a new output directory:

```bash
surface-atlas register-library ./library-registration.json \
  --output ./registered-library --json
```

The command writes the output atomically and refuses an existing directory. It
creates `molecular-library.json`, `registration.json`, and a `libraries/`
directory containing source copies and individual SDF records. FASTA sequences
are stored in the collection, with the original FASTA file retained alongside it.

## Extend an imported library

Use a previous import's collection as the base and choose a new output directory:

```bash
surface-atlas register-library ./additional-inputs.json \
  --base-library ./registered-library/molecular-library.json \
  --output ./combined-library --json
```

Both manifests must use the same `atlas_id`. The importer retains the base
records and copies their referenced files after checking their sizes and hashes.
Those files must remain below the base collection's directory. Duplicate record
IDs stop the import; the existing library stays unchanged.

## Use the collection in a new atlas

Create an atlas with the manifest's `atlas_id`, then copy the reviewed collection:

```bash
surface-atlas init library-study ./disease-surface-atlas --disease "Your disease"
cp ./registered-library/molecular-library.json \
  ./disease-surface-atlas/molecular-library.json
```

The collection refers to files below `./registered-library`. Configure that
directory as the atlas's local artifact root before validation or reporting:

```bash
python - <<'PY'
import json
from pathlib import Path

atlas = Path("./disease-surface-atlas").resolve()
artifact_root = Path("./registered-library").resolve()
(atlas / ".surface-atlas-local.json").write_text(
    json.dumps({"artifact_root": str(artifact_root)}, indent=2) + "\n",
    encoding="utf-8",
)
PY

surface-atlas validate ./disease-surface-atlas --json
surface-atlas report ./disease-surface-atlas \
  --output-root ./surface-atlas-reports --run-id library-review --json
```

On Windows PowerShell, create the atlas, copy the collection, and set the
artifact directory:

```powershell
.\.venv\Scripts\surface-atlas.exe init library-study .\disease-surface-atlas --disease "Your disease"
Copy-Item .\registered-library\molecular-library.json `
  .\disease-surface-atlas\molecular-library.json
.\.venv\Scripts\python.exe -c "import json; from pathlib import Path; atlas = Path('./disease-surface-atlas').resolve(); artifact_root = Path('./registered-library').resolve(); (atlas / '.surface-atlas-local.json').write_text(json.dumps({'artifact_root': str(artifact_root)}, indent=2) + '\n', encoding='utf-8')"
.\.venv\Scripts\surface-atlas.exe validate .\disease-surface-atlas --json
.\.venv\Scripts\surface-atlas.exe report .\disease-surface-atlas `
  --output-root .\surface-atlas-reports --run-id library-review --json
```

`.surface-atlas-local.json` stays beside the local atlas. The validator and
report use its `artifact_root` to resolve the registered file paths and verify
their checksums. Keep the directory available while working with the atlas.
