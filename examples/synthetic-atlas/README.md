# Synthetic Surface Atlas fixture

This invented workspace demonstrates target pages and report navigation.
It contains three fictional targets: Ember, Lantern, and Orbit. Across the
workspace, two intervention records, two structure records, and one planned
screen show how the collections connect. Orbit has no structure record, so
you can also inspect how the report displays missing information.

Validate and render it with:

```bash
surface-atlas validate examples/synthetic-atlas --json
surface-atlas report examples/synthetic-atlas \
  --output-root ./surface-atlas-reports --run-id synthetic-v1 --json
```
