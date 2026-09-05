# 3Dmol.js dependency

The report uses 3Dmol.js 2.5.5 for an optional molecular preview. The browser loads
the local bundle after the reader selects **View in 3D**. It makes no requests to
external structure databases or CDNs.

- Project: https://github.com/3dmol/3Dmol.js
- Source tag: `2.5.5`
- Source commit: `c26e390544b6388f86e50387cd4565759b4da0df`
- Official package: https://registry.npmjs.org/3dmol/-/3dmol-2.5.5.tgz
- Package SHA-512 integrity: `kqNHouGqq3YfW58174tdERvm0XYTmP0tavQKOqIw1ouc2OJ7epkXEFrtEkVXV0clBZT2Ze2xHRC/qxX0u0qCdw==`
- Retrieved: 2026-09-04
- API reference: https://3dmol.org/doc/GLViewer.html

The npm package identifies the official repository in its package manifest.
Its minified browser build is copied unchanged as `3Dmol-2.5.5.min.js`.
`3Dmol-LICENSE.txt` contains the project's BSD-3-Clause license and incorporated
code notices. `3Dmol-min.js.LICENSE.txt` contains the notices referenced by the
minified bundle. Both files must accompany redistributed report assets.

| File | SHA-256 |
| --- | --- |
| `3Dmol-2.5.5.min.js` | `f7cc78921ae72e7623e89cdd111434f58c2efddd2ffda1cd212644b406fb8016` |
| `3Dmol-LICENSE.txt` | `4c6eaaed856f3f28a3b1a98e74f4a8a71618de7d51ea4155c29f6f793bcef861` |
| `3Dmol-min.js.LICENSE.txt` | `ae3bfc688d0c9687b76e0ecc7fece0b393bcb4acf2aee09e19dda697eaa10b16` |

The preview accepts packaged PDB, mmCIF, and SDF artifacts, limits downloads to
8 MiB, and limits rendering to 60,000 atoms. It displays the first model without
building biological assemblies. The report retains each source identifier and
evidence class. Molecular rendering does not change either field.
