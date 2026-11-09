# S09 fixed Lean/Mathlib environment

This directory is the build input for the S09 rational-polynomial formal
backend. It pins Lean 4.19.0 and Mathlib v4.19.0; it does not claim that these
are the latest releases.

- Lean release: https://github.com/leanprover/lean4/releases/tag/v4.19.0
- Lean commit: `6caaee842e9495688c1567e78c0e68dbb96942aa`
- Mathlib release: https://github.com/leanprover-community/mathlib4/tree/v4.19.0
- Mathlib commit: `c44e0c8ee63ca166450922a373c7409c5d26b00b`
- Mathlib toolchain: `leanprover/lean4:v4.19.0`
- Lean archive: `lean-4.19.0-linux.tar.zst`, SHA-256
  `6fe3ce97a58f44e2b3567d455b994eacec5bfe9ae7774f2a573444480ba813fe`
- Base: `ubuntu:24.04@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852`

The similarly named `linux_x86` release archive is not the amd64 toolchain: its
`bin/lean` has a 32-bit ELF interpreter and fails on Ubuntu 24.04. The build uses
the amd64 `linux` archive, whose binary was checked to report Lean 4.19.0 and
Lake 5.0.0-6caaee8.

Run image construction only when no previous `mathagent-lean-prepare`
container exists. The named preparation container has a persisted bind mount
for `status.json` and `prepare.log`; do not start a duplicate cache install.
After completion, construct the image from the prepared filesystem and preserve
the `deployment.json` identity separately from the non-circular image label.

Runtime contract is offline, read-only, non-root, with no Linux capabilities.
The image contains Lean, Mathlib, dependencies and cache. The runtime accepts
Lean source on stdin and uses the native `Lean.collectAxioms` implementation
underlying `#print axioms`; source text search alone is never an audit.

Allowed dependency axioms for the first release are:

- `propext`
- `Classical.choice`
- `Quot.sound`

`sorryAx` and any other unregistered axiom are violations. The runtime wrapper
checks the exact image ID and build-manifest label, collects axioms for the named
theorem, and requires the deployment-record identity check. A kernel
success without this audit is not L2.
