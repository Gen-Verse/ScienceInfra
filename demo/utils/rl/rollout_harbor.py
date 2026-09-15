"""Rollout collection over sciaccel-rl tasks, through Harbor.

This is the bridge an RL trainer plugs into: hand it task paths and an agent
(the policy being trained, served behind an OpenAI-compatible endpoint such
as vLLM), get back one record per trajectory with the graded reward dict.
It follows the interface Harbor's own RL docs recommend (a Job per rollout
batch); SkyRL's Harbor integration is the worked example of wiring this into
a trainer.

Written against harbor 0.18.x (`uv tool install harbor` / `pip install harbor`).

Smoke test, no model or API key needed — the oracle plays the policy and
must come back with reward 1.0, the nop agent with 0.0:

    python utils/rl/rollout_harbor.py --task envs/laps/tasks/acceleration/laps-accel-cpu --agent oracle
    python utils/rl/rollout_harbor.py --task envs/laps/tasks/acceleration/laps-accel-cpu --agent nop

Training rollouts (terminus-2 is Harbor's simple command-loop harness, the
natural choice for a policy under training; token/mask collection for the
trainer comes from vLLM-side interception or agent metadata — see
https://harborframework.com/docs/training-workflows/rl):

    python utils/rl/rollout_harbor.py --task envs/laps/tasks/acceleration/laps-accel-cpu \
        --agent terminus-2 --model "hosted_vllm/<model>" \
        --n-attempts 8 --n-concurrent 8

Reward keys (written by the task's verifier, see tests/test.sh):
    reward            0..1 graded correctness — the default training signal
    equivalence_pass  0|1  strict all-checks gate
    speedup           advisory, self-reported; gate on equivalence_pass and
                      fold into the return trainer-side if you train for it
    check_*           per-check scores, for re-weighting
"""

import argparse
import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

from harbor.job import Job
from harbor.models.job.config import AgentConfig, JobConfig
from harbor.models.trial.config import TaskConfig


@dataclass
class RolloutRecord:
    task_name: str
    trial_name: str
    reward: float
    rewards: dict = field(default_factory=dict)
    trial_uri: str | None = None
    exception: str | None = None


async def collect_rollouts(
    task_paths: list[str],
    agent: str = "terminus-2",
    model: str | None = None,
    n_attempts: int = 1,
    n_concurrent: int = 4,
    jobs_dir: str = "jobs",
    agent_kwargs: dict | None = None,
) -> list[RolloutRecord]:
    """Run n_attempts trials of every task and return one record per trial.

    GRPO-style trainers: set n_attempts to the group size — the per-task
    groups needed for advantage normalisation come back labelled by
    task_name.
    """
    config = JobConfig(
        jobs_dir=Path(jobs_dir),
        tasks=[TaskConfig(path=p) for p in task_paths],
        agents=[
            AgentConfig(
                name=agent,
                model_name=model,
                kwargs=agent_kwargs or {},
            )
        ],
        n_attempts=n_attempts,
        n_concurrent_trials=n_concurrent,
    )
    job = await Job.create(config)
    result = await job.run()

    records = []
    for tr in result.trial_results:
        rewards = (
            dict(tr.verifier_result.rewards)
            if tr.verifier_result and tr.verifier_result.rewards
            else {}
        )
        records.append(
            RolloutRecord(
                task_name=tr.task_name,
                trial_name=tr.trial_name,
                reward=float(rewards.get("reward", 0.0)),
                rewards=rewards,
                trial_uri=tr.trial_uri,
                exception=(
                    tr.exception_info.exception_message
                    if tr.exception_info
                    else None
                ),
            )
        )
    return records


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--task", action="append", required=True,
                    help="task directory; repeat for a batch")
    ap.add_argument("--agent", default="oracle",
                    help="harbor agent name (oracle | nop | terminus-2 | ...)")
    ap.add_argument("--model", default=None,
                    help="model for the agent, e.g. hosted_vllm/<name>")
    ap.add_argument("--n-attempts", type=int, default=1)
    ap.add_argument("--n-concurrent", type=int, default=4)
    ap.add_argument("--jobs-dir", default="jobs")
    args = ap.parse_args()

    records = asyncio.run(
        collect_rollouts(
            task_paths=args.task,
            agent=args.agent,
            model=args.model,
            n_attempts=args.n_attempts,
            n_concurrent=args.n_concurrent,
            jobs_dir=args.jobs_dir,
        )
    )
    for r in records:
        print(json.dumps(r.__dict__, default=str))
    if records:
        mean = sum(r.reward for r in records) / len(records)
        print(f"# {len(records)} rollouts, mean reward {mean:.4f}")


if __name__ == "__main__":
    main()
