# RL recipe

The training half of ScienceInfra: the agent loop, the episode runner, the
verifier-derived reward, and the failure classifier. PSRL runs the optimizer
underneath.

## Why this setting needs its own recipe

Three properties of outcome-graded repair drive every choice here, and they are
what separate it from single-turn verifiable-reward RL.

| Property | Consequence |
|---|---|
| Reward is **outcome-only** | One scalar in `[0,1]` after the episode ends. No per-turn signal, so a learned critic would regress a terminal scalar through tens of thousands of tokens. GRPO instead of PPO. |
| Trajectories are **long and variable** | Tens of thousands of tokens over roughly 30 turns, with more than an order of magnitude of spread inside one batch. |
| Episodes hit **hard budget cutoffs** | An episode ends when it finishes, exhausts the turn cap, or exhausts the response budget. The last two are facts about the harness, not verdicts on the policy. |

## Mask budget cutoffs, do not penalize them

That third row is the one that decides whether a run converges. Grading a budget
cutoff as a policy failure puts negative advantage on trajectories the harness
stopped mid-repair, and token-mean aggregation weights that penalty by length.
The cheapest way for gradient descent to shed it is to emit shorter turns, which
spends the turn cap faster and produces more truncation. Runs collapse, and the
symptom that reaches the dashboard is rising entropy, which sends the
investigation to the wrong layer.

**The fix is to mask.** Zero the loss mask of every trajectory a budget cut off,
and keep its reward in the group baseline so finishers still get an honest
positive advantage. Dropping the rows instead collapses that baseline.
`overlong_filtering=True` in the launch scripts is this, and it is the one
setting not to change.

## Results

Qwen3.5-4B, GRPO at hint level L1, one run per environment, 24 GPUs across three
nodes split 8 for generation and 16 for training. Reward is the shaped
`reward_repair`, so means carry partial credit and are **not** pass rates.

![LAPS training diagnostics](../../figures/rl_training_laps.svg)

![MITgcm-biogeo training diagnostics](../../figures/rl_training_mitgcm_biogeo.svg)

<sub>Regenerate both: `python -m scienceinfra.plotting.rl_training`. The metric
table is committed inside that module.</sub>

Means over the first and last five recorded steps of each run:

| Environment | Reward | Finisher | Truncation (%) | Turns | Validation, base to RL |
|---|---|---|---|---|---|
| LAPS | 0.427 to 0.828 | 0.683 to 0.883 | 39.5 to 6.6 | 34.7 to 24.5 | 0.357 to 0.857 |
| MITgcm-biogeo | 0.381 to 0.597 | 0.571 to 0.747 | 34.1 to 23.8 | 32.2 to 31.2 | 0.286 to 0.571 |

The gain reaches the held-out split rather than staying in training reward, and
finisher-only reward rises alongside the mean, so the policy repairs more tasks
rather than finishing a shifting subset. Tokens per turn holds steady while turns
per episode holds or falls, which is the direct test of the mechanism above: with
the spurious length gradient removed, the policy gains nothing from shortening a
turn.

The same recipe on the same bank without masking:

| | unmasked | masked |
|---|---|---|
| Mean reward | 0.339 to 0.573 to 0.078 | 0.487 to 0.914 |
| Tokens per turn | 1125 to 327 | 1095 to 1165 (flat) |
| Truncation rate | 29% to 39% | 28.9% to 2.3% |
| Entropy | rising | 0.586 to 0.348 |

One lever is still on the table. The fraction of groups with zero reward variance
grows as the policy improves, reaching 47.5% on LAPS, so a growing share of each
batch contributes no gradient. Dynamic sampling resamples exactly those groups
and is implemented but left off, so that masking could be measured in isolation.

## Files

| Path | What it does |
|---|---|
| [`agent_loop.py`](agent_loop.py) | The loop PSRL instantiates, one episode per prompt |
| [`agent.py`](agent.py) | Harbor agent, with turn and budget accounting |
| [`runner.py`](runner.py) | Builds the Harbor job for one task and runs it |
| [`reward.py`](reward.py) | Reads the verifier's scalar out of the Harbor result |
| [`exceptions.py`](exceptions.py) | Maps harness faults to a terminate reason |
| [`config.py`](config.py) | Resolves the launch configuration |

## Gotchas

- **`max_model_len` must equal the training budget exactly.** It reaches the
  harness as `max_input_tokens`, so headroom is budget the agent spends, and the
  trainer then receives a response longer than `max_response_length`.
- **An infrastructure fault must not reach the gradient.** The classifier decides
  abort against error, and an abort tears down the whole GRPO group. A fault
  graded as a zero teaches the policy that a working repair failed.
