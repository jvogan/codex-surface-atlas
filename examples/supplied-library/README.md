# Supplied-library example

This example registers two compound records and a synthetic peptide, then
saves their source files and hashes.

Run the registrar from the repository root with a new output directory:

```bash
surface-atlas register-library ./examples/supplied-library/registration.json \
  --output ./registered-library-example --json
```

The command writes `molecular-library.json`, `registration.json`, and copied
input artifacts below `./registered-library-example`. See [Supplied
libraries](../../docs/supplied-libraries.md) to add the reviewed collection to
an atlas and configure its artifact root.
