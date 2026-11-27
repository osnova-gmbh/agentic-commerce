# Factory context

This is the canonical thin resident-agent template.

Preserve these invariants when generating an agent:

1. Domain source under `src/<package>/` does not import `cogit_runtime`, web
   frameworks, SQL infrastructure, or provider SDKs.
2. `main.py` remains a composition root around `CogitRuntimeApp`.
3. Manifest and decorated actions retain exact parity.
4. Writes are idempotent and approval-gated where policy requires.
5. Evals remain black-box HTTP data and are enforced in CI.
6. Server and worker use the same manifest and image.

Replace synthetic domain logic and prompts; do not copy generic runtime
machinery into the generated repository.
