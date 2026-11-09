FROM mathagent-lean-stage-base:4.19.0
ARG BUILD_MANIFEST_SHA256
LABEL mathagent.lean.policy="docker-lean-v1" \
      mathagent.lean.lean_version="4.19.0" \
      mathagent.lean.lean_commit="6caaee842e9495688c1567e78c0e68dbb96942aa" \
      mathagent.lean.mathlib_version="v4.19.0" \
      mathagent.lean.mathlib_commit="c44e0c8ee63ca166450922a373c7409c5d26b00b" \
      mathagent.lean.toolchain="leanprover/lean4:v4.19.0" \
      mathagent.lean.template_version="rational-polynomial-v1" \
      mathagent.lean.build_manifest_sha256="${BUILD_MANIFEST_SHA256}" \
      mathagent.lean.policy_allowed_axioms="propext,Classical.choice,Quot.sound"
COPY runtime.sh /usr/local/bin/s09-run
RUN chmod 0755 /usr/local/bin/s09-run && mkdir -p /opt/s09/home
USER 65534:65534
WORKDIR /work
ENTRYPOINT ["/usr/local/bin/s09-run"]
