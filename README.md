<div align="center">

# ScienceInfra

### Open Learning Infrastructure for Discovery Intelligence

**Turn scientific experience into agent capability.**

[English](README.md) · [简体中文](README.zh-CN.md)

[Paper](https://arxiv.org/abs/2609.19134) · [ScienceIDE](https://github.com/aitofound/ScienceIDE) · [Quickstart](#quickstart) · [Roadmap](#roadmap) · [Documentation](#documentation)

</div>

**ScienceInfra is an ongoing infrastructure project for training and evaluating scientific agents.** Originating from the training and evaluation component of [ScienceIDE](https://github.com/aitofound/ScienceIDE), it connects scientific task banks, containerized execution, verifiable rewards, and agent learning.

| Project | Focus |
|---|---|
| **[ScienceIDE](https://github.com/aitofound/ScienceIDE)** | Turn scientific code and domain expertise into executable environments and validated tasks. |
| **ScienceInfra** | Turn those environments into reusable training and evaluation workflows, with a long-term focus on execution, verification, and learning systems. |

Our goal is to make scientific experience a scalable resource for **Discovery Intelligence**—with infrastructure that grows across environments, agent harnesses, and learning methods.

![ScienceInfra: scientific experience becomes agent capability](figures/discovery-infra.svg)

## What makes ScienceInfra distinct

- **Scientific feedback for learning.** Connect executable scientific checks to rewards, including baseline-aware partial credit for code repair.
- **Long-horizon agent training.** Integrate asynchronous GRPO with explicit handling of variable-length episodes and budget-truncated trajectories.
- **Reliable execution and evaluation.** Separate infrastructure failures from policy outcomes; support container cache warming and independent checkpoint evaluation.
- **Reusable integration interfaces.** Keep task packages, agent loops, and reward hooks separate. The current stack integrates PSRL, Harbor, and vLLM.

The current release supports **task preparation → agent execution → online RL → evaluation**, with bundled LAPS and MITgcm-biogeo demos. See the [architecture and experiments](USAGE.md) for implementation details and reported results.

## Quickstart

Start with the bundled LAPS demo; environment validation requires **Python 3.11+, Docker, and Harbor**, with no model or GPU needed.

```bash
git clone https://github.com/Gen-Verse/ScienceInfra.git
cd ScienceInfra
pip install -e .

bash scripts/prepare/prepare_all.sh \
    --repo demo --envs laps --stages compile,lines,dataset

bash scripts/eval/eval_standalone.sh \
    --dataset data/laps/repair_easy/all/L1.parquet \
    --agent oracle --limit 1 -n 1 --output-dir outputs/anchor_oracle
```

The oracle check should score **1.0**. Follow the [usage guide](USAGE.md#quickstart) to check the nop baseline, set up PSRL, and run training. The RL launcher is a cluster recipe and must be configured for your hardware.

## Roadmap

**ScienceIDE is our starting point. ScienceInfra's long-term focus is the shared infrastructure for scientific agent learning.**

| Direction | Planned development |
|---|---|
| **Scale execution** | Reusable environment images, cache reuse, and resource-aware scheduling for expensive scientific episodes. |
| **Strengthen verification** | Validity checks, reward diagnostics, and verification of task isolation. |
| **Broaden learning workflows** | Trajectory export, SFT integration, and additional training and harness adapters. |
| **Learn across environments** | Curriculum and sampling support, held-out codebase evaluation, and feedback into task development. |
| **Extend scientific tasks** | Expand the learning pipeline from code repair toward calibration, implementation, acceleration, and multi-step research. |

These are development directions; current functionality is described above. We welcome contributions that make the infrastructure useful across scientific domains and future research projects.

## Documentation

| Guide | Contents |
|---|---|
| [Usage guide](USAGE.md) | Installation, demos, experiments, training setup, and troubleshooting |
| [Task preparation](scienceinfra/datasets/README.md) | Task-bank compilation, dataset splits, and cache warming |
| [RL recipe](scienceinfra/rl/README.md) | Agent loop, scientific rewards, budget handling, and training diagnostics |
| [Evaluation](scienceinfra/eval/README.md) | Baselines, checkpoint evaluation, and output formats |
| [Bundled demos](demo/README.md) | LAPS and MITgcm-biogeo environments |

## Contribute

We welcome contributions in **scientific environment integration, execution systems, verifiers, training adapters, and evaluation**. [Open an issue](https://github.com/Gen-Verse/ScienceInfra/issues) or [submit a PR](https://github.com/Gen-Verse/ScienceInfra/pulls). Include oracle/nop checks for new environments, and document rewards, splits, and budgets for learning changes.

⭐ Star the repository to follow ongoing releases and help build open infrastructure for discovery intelligence.

## Citation and acknowledgments

For the scientific environments, methodology, and reported experiments, cite the [ScienceIDE work](https://arxiv.org/abs/2609.19134). When using ScienceInfra, also link to this repository and record the commit used.

<details>
<summary>BibTeX</summary>

```bibtex
@article{geng2026scienceide,
  title={ScienceIDE: Turning World's Scientific Codebase into Agent Learnable Environments},
  author={Geng, Hejia and Huang, Zesen and Li, Haoyang and Li, Wenbin and Wu, Koutian and Zhou, Zihan and Pang, Yuanbo and Liu, Weihao and Xu, Zigong and Li, Zhiping and Zhang, Zongzheng and Dong, Chuanfei and Sun, Jiankai and Zheng, Tianzhe and Xie, Fengyu and Ma, Yue and Shi, Yueheng and Xie, Tong and Di, Zonglin and Liu, Xianrong and Gao, Qucheng and Liu, Yimin and Pan, Jiaming and Huang, Sheng and Ma, Xiao-Han and Yuan, Lanqing and Zhu, Zhenlin and Liu, Ziang and Xu, Ziyang and Wang, Junkai and Liang, Kangkai and Xian, Jiayi and Zhao, Zehong and Xu, Liuwei and Xie, Jingxu and Zhang, Peijin and Gao, Qiang and Xing, Chengyi and Zhao, Zhe and Wang, Xi and Xing, Yaopeng and Meng, Xing and Yin, Zhenfei and Wu, Yingcheng and Yang, Ling},
  journal={arXiv preprint arXiv:2609.19134},
  year={2026}
}
```

</details>

Built on [PSRL](https://github.com/psrl-project/psrl), [Harbor](https://github.com/laude-institute/harbor), and [vLLM](https://github.com/vllm-project/vllm). We thank [PKU-DAIR](https://github.com/PKU-DAIR) for their support and collaboration in providing the RL infrastructure. Thanks to the ScienceIDE contributors and scientific software maintainers.

**License:** [Apache 2.0](LICENSE). Third-party scientific codebases retain their own licenses.
