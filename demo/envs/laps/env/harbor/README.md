# env/harbor — the compile-time defaults for this env's tasks

Everything a harbor task dir needs that is NOT the task's own lives here,
once. `utils/harbor/to_harbor.py` stamps it into every sparse source task
at compile time (source `tasks/<category>/<name>/` -> `build/laps/...`).

    agent.Dockerfile        template: the agent image. A prep stage clones the
                            pin, applies upstream-patches and the task's
                            defect, strips .git and ungraded sibling trees;
                            the final stage carries toolchain + defective
                            tree + cases + validation. The defect spec never
                            reaches the final image.
    verifier.Dockerfile     template: reference stage (clean build runs the
                            graded cases in situ) -> straw stage (defective
                            build runs them, graded by the task's grade.py ->
                            floor.json) -> grader image.
    solve.sh                template: the oracle — apply fix.json, rebuild,
                            run, deliver.
    task.toml               template used by the FACTORY when it emits a
    instruction-repair.md   source task (the emitted files are then per-task
    instruction-restore.md  and copied verbatim by the compiler).
    apply_defect.py         shared script: apply a {edits}|{diff} transform.
    grade_floor.py          shared script: grade the straw run -> floor.json.

Tokens (`@NAME@`, `@CHECKS_SH@`, `@STRIP@`, `@REF_BUILDS@`, `@STRAW_BUILDS@`,
`@BUILDS@`, `@APT_MIRROR@`, `@DIGEST@`, `@REPO@`, `@SHA@`, ...) are filled by
the compiler from the task's `task.toml` (tree, graded checks, canary) and
its options (`--apt-mirror`). `../scoring/grade.py` is the grading base the
compiler specialises per task (CHECKS subset + canary + reward_repair).

Edit a file here, recompile, and every task changes — there is no second
copy anywhere in git. The build output is byte-stable (same source + same
env -> same bytes), which is the regression harness for any edit.

## The base-image seam (reserved, not built)

`utils/harbor/to_harbor.py --base-image` is reserved for the fleet mode where the shared
stages come from prebuilt env images instead of being rebuilt per task:

    agent.Dockerfile    prep stage + toolchain apt stage   -> FROM laps-agent-base
    verifier.Dockerfile reference stage (toolchain + clone + build + run
                        graded cases)                     -> FROM laps-verifier-base-{2d,3d}

Per task there would remain only: apply the defect (agent), the straw stage
(verifier), and grade.py/floor.json. Docker layer caching already gives
one-machine builds this property; the base images buy it across a fleet via
a registry. Wire it when a fleet exists; until then the flag refuses.
