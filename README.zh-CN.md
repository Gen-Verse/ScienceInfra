<div align="center">

# ScienceInfra

### 面向发现智能的学习基础设施

**让科学智能体在可执行环境中，通过真实代码与可验证反馈持续提升能力。**

[English](README.md) · [简体中文](README.zh-CN.md)

[ScienceIDE 项目](https://aitonomy.org/projects/scienceide) · [ScienceIDE 仓库](https://github.com/aitofound/ScienceIDE) · [实验结果](#实验结果) · [快速开始](#快速开始) · [发展路线](#发展路线) · [参与共建](#参与共建)

</div>

![ScienceInfra 愿景：将科学经验转化为智能体能力，让更强的智能体回到科学实践](figures/discovery-infra.svg)

**ScienceInfra 是 ScienceIDE 工作中的训练与评测基础设施组件**，对应论文 *ScienceIDE: Scaling Scientific Experience toward 1,000 Executable Environments*。它连接科学任务库、容器化智能体执行、科学验证奖励、异步强化学习与独立评测。

**我们的长期目标是构建面向 Discovery Intelligence（发现智能）的可复用学习基础设施。** 当前实现从科学代码场景的 Agentic RL 出发，后续将重点发展执行规模化、科学验证，以及跨智能体和学习流程的科学经验复用。

⭐ **欢迎 Star，关注 ScienceInfra 的持续建设**，共同构建让智能体从科学中学习的基础设施。

## 为什么需要 ScienceInfra：Chat → Code → Discovery

文本为语言模型提供了对话经验。代码仓库、编译器和测试让编程成为可交互的学习环境。**走向发现智能，需要更丰富的经验来源：智能体必须行动、实验、检查证据，并从反馈中改进。**

科学提供了这样的机会，但科学代码仓库不会自动成为训练环境。依赖与工具链需要可靠运行，科学结果需要经过校准的检查，耗时且长短不一的任务执行需要转化为有效的学习信号。

ScienceIDE 将领域专家知识转化为可执行环境和有效任务，解决科学经验的供给问题。**ScienceInfra 将这些经验接入智能体学习闭环。** 二者共同服务于双向愿景：**Science for AI**，通过科学反馈发展智能体能力，以及 **AI for Science**，让改进后的智能体回到科学实践。

## 与 ScienceIDE 的关系

| 层次 | 职责 | 入口 |
|---|---|---|
| **ScienceIDE** | 科学环境构建、任务工厂、有效性验证及整体研究体系 | [项目主页](https://aitonomy.org/projects/scienceide) · [仓库](https://github.com/aitofound/ScienceIDE) |
| **ScienceInfra** | 任务库准备、智能体执行、奖励接口、在线 RL 与模型评测 | **本仓库** |
| **学习后端** | 基于 veRL 的 PSRL 提供异步 rollout 与优化，vLLM 提供模型生成 | [PSRL](https://github.com/psrl-project/psrl) |
| **执行框架** | 容器化工具交互与 verifier 执行 | [Harbor / Terminus-2](https://github.com/laude-institute/harbor) |

ScienceIDE 论文报告了来自 **27 个代码库的 64 个环境、2,812 个任务**。**1,000 个环境是后续扩展目标**。这些数字描述 ScienceIDE 整体工作。本仓库提供基础设施代码与运行方案，科学任务库需要另外准备。

当前 ScienceIDE 仓库标注为 **placeholder release**，包含任务规范、有效性检查和示例。该版本尚未包含完整任务库及任务生产流水线。本项目所需的任务库格式见[快速开始](#快速开始)。

## 现在可以做什么

| 能力 | 用途 | 入口 |
|---|---|---|
| **准备科学任务库** | 编译任务、解析缺陷提示、生成数据划分，并预热容器缓存 | [数据准备](scienceinfra/datasets/README.md) |
| **运行长程科学任务** | 让智能体阅读与修改真实代码、调用工具，并获得科学反馈 | [执行器](scienceinfra/rl/runner.py) |
| **通过科学奖励训练** | 将数值验证反馈经由可配置的 agent loop 和 reward 接口接入异步 GRPO | [RL 方案](scienceinfra/rl/README.md) |
| **评测基座与训练后模型** | 独立运行评测，记录逐任务结果、类别汇总与基础设施错误 | [评测指南](scienceinfra/eval/README.md) |

### 针对科学工作负载的设计

- **以科学行为作为奖励来源。** Verifier 重新编译、执行代码，并按任务规定检查科学输出。修复奖励考虑未修复程序的基线，支持部分得分。
- **显式处理长轨迹的预算截断。** 当前方案将预算截断轨迹从 token loss 中屏蔽，同时保留其奖励参与组内基线计算。
- **区分基础设施故障与模型结果。** 执行器和故障分类器分别处理环境错误与策略结果，避免执行异常被默认为学习目标。
- **支持昂贵环境的运行管理。** 数据准备包含缓存预热，启动配置控制哪些节点承载任务执行。
- **分离科学任务与学习逻辑。** 任务包定义科学问题，agent loop 和 reward hook 通过配置接入 PSRL。

<details>
<summary><strong>查看执行与训练架构</strong></summary>

![ScienceInfra 执行与训练架构](figures/overview.svg)

PSRL 提供异步 rollout 管理、token 采集、权重传输和 GRPO 训练器。Harbor 执行任务。vLLM 提供模型生成。ScienceInfra 提供这些组件之上的科学任务接入层。

</details>

## 实验结果

**在两个科学环境中，科学反馈提升了模型在留出任务上的验证奖励。**

ScienceIDE 论文比较了 **Qwen3.5-4B** 基座与经过 30 步 GRPO 的模型。RL 直接从基座开始，没有使用 SFT 初始化。

| 环境 | 科学场景 | 实际评测的留出任务 | 基座奖励 | RL 后奖励 | 提升 |
|---|---|---:|---:|---:|---:|
| **LAPS** | 伪谱 Hall-MHD | 14 | 0.357 | **0.857** | **+0.500** |
| **MITgcm-biogeo** | 海洋生物地球化学 | 21 | 0.286 | **0.571** | **+0.285** |

指标为 **0 到 1 范围内、允许部分得分的平均 shaped verifier reward**。基座和 RL 模型使用一致的 harness 与缺陷定位提示。这是训练环境内部的留出评测，每个环境一组运行，尚未证明跨未知代码库的迁移能力，也未测量多随机种子的不确定性。无提示的 ScienceIDE-Hard 排行榜属于另一项评测。

<details>
<summary><strong>训练曲线与方案细节</strong></summary>

![LAPS 训练诊断](figures/rl_training_laps.svg)

![MITgcm-biogeo 训练诊断](figures/rl_training_mitgcm_biogeo.svg)

MITgcm-biogeo 原始划分含 23 个验证任务，论文上述留出比较实际评测 21 个，因此训练诊断图与留出评测表的样本数不同。

预算截断处理与训练诊断见 [RL 方案](scienceinfra/rl/README.md)。运行 `python -m scienceinfra.plotting.rl_training` 可重绘图表，数据表已保存在对应模块中。

</details>

## 快速开始

建议先验证一个科学环境的执行链路。模型训练和推理服务还需要额外的计算资源及后端配置。

### 1. 安装并准备输入

- 本包要求 **Python 3.11+**。训练时采用 PSRL 所要求的兼容 Python/CUDA 环境。
- 每台运行任务的机器均需要 **Docker**，当前 Python 环境需要安装 Harbor。
- **科学任务库**：[`demo/`](demo/README.md) 已内置两个环境，下列命令无需另外准备任务库即可运行。更多科学环境与任务见 [ScienceIDE](https://github.com/aitofound/ScienceIDE)。
- 训练及模型评测需要安装 **[PSRL](https://github.com/psrl-project/psrl#-quick-start)** 及其训练、推理依赖。

<details>
<summary><strong>从源码安装 PSRL</strong></summary>

PSRL 未发布到 PyPI。请先按其[安装指南](https://github.com/psrl-project/psrl#-quick-start)从源码安装：

```bash
# Rust 是编译前置依赖。
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

conda create -n psrl python=3.12 && conda activate psrl

git clone https://github.com/psrl-project/psrl.git && cd psrl
bash scripts/install_basic.sh        # vLLM、veRL 及核心依赖
bash scripts/install_nixl.sh         # RDMA 权重同步
bash scripts/install_megatron.sh     # Megatron、TransformerEngine
bash scripts/install_lmcache.sh      # LMCache
python -m pip install -e .           # 安装 PSRL 本身
```

也可以使用 Docker 镜像，从而跳过上述编译步骤。当前镜像 tag 以 [PSRL README](https://github.com/psrl-project/psrl) 为准。

</details>

```bash
git clone https://github.com/Gen-Verse/ScienceInfra.git
cd ScienceInfra
pip install -e .
```

在每个 worker 的环境中安装 ScienceInfra，确保 Ray 能通过包路径导入 agent loop。上述安装命令只安装本包及其依赖，完整 PSRL 运行栈需另行准备。

### 2. 构建一个环境

内置的 LAPS demo 无需外部任务库，也不需要 GPU。

```bash
bash scripts/prepare/prepare_all.sh \
    --repo demo --envs laps --stages compile,lines,dataset
```

该命令把授权任务编译为 Harbor 任务，并把 Parquet 写入 `data/laps/repair_easy/`。若要使用 MITgcm demo，先按 [`demo/README.md`](demo/README.md) 恢复其二进制输入，再改用 `--envs mitgcm-biogeo`。

生成的 Parquet 包含任务的绝对路径，运行任务的节点必须能访问这些路径。多节点缓存预热与重建流程见[数据准备指南](scienceinfra/datasets/README.md)。

### 3. 无需模型或 GPU，验证执行链路

```bash
# 先验证一个任务，再移除 --limit 1 检查整个任务库。
bash scripts/eval/eval_standalone.sh \
    --dataset data/laps/repair_easy/all/L1.parquet \
    --agent oracle --limit 1 -n 1 --output-dir outputs/anchor_oracle

bash scripts/eval/eval_standalone.sh \
    --dataset data/laps/repair_easy/all/L1.parquet \
    --agent nop --limit 1 -n 1 --output-dir outputs/anchor_nop
```

预期归一化修复得分为 **oracle = 1.0、nop = 0.0**。首次执行会构建容器镜像，需要预留编译时间。验证失败时，应先解决环境问题，再评测模型。

### 4. 运行 RL 方案

当前训练脚本采用 **3 节点 × 8 GPU，其中 8 张用于生成、16 张用于训练**。启动前，请根据硬件调整 [`train_grpo.sh`](scripts/rl/train_grpo.sh) 中的 deployment 配置，并完成 PSRL/Ray 集群设置。按照数据准备指南预热每个执行节点的任务镜像。

```bash
HF_MODEL_PATH=/absolute/path/to/Qwen3.5-4B \
DATA_DIR="${PWD}/data/mitgcm-biogeo/repair_easy" \
HINT_LEVEL=L1 \
    bash scripts/rl/train_grpo.sh
```

训练后模型评测见[评测指南](scienceinfra/eval/README.md)。比较结果时应对齐提示、thinking 模式、上下文窗口与轮数预算。训练与独立评测脚本的默认配置有所不同。

## 发展路线

**ScienceIDE 是起点，ScienceInfra 将持续聚焦科学智能体学习的基础设施建设。** 以下是发展方向，具体范围将结合实验与社区贡献逐步完善。

| 方向 | 后续建设重点 |
|---|---|
| **规模化执行** | 可复用 verifier 镜像、更高效的缓存复用，以及面向昂贵科学任务的资源调度 |
| **可靠科学反馈** | 数据构建时的有效性检查、细粒度奖励诊断，以及任务隔离效果的验证 |
| **更丰富的学习任务** | 从当前修复方案拓展至参数校准、实现、加速及多步骤科学流程 |
| **可复用学习接口** | 简化轨迹导出、SFT 数据使用，以及更多训练框架和 harness 的接入 |
| **跨环境学习** | 课程与采样机制、留出代码库评测，以及将新增经验反馈给任务开发的接口 |

当前代码重点是任务准备、在线 RL 和评测。上述更广泛的接口与任务覆盖属于后续建设方向，当前集成的训练后端为 PSRL。

## 参与共建

欢迎 **AI/RL 研究者、系统工程师与科学软件专家**参与。

- **接入科学环境：** 定义有意义的任务、运行环境、科学观测量和可执行验收标准。
- **改进基础设施：** 降低环境启动成本、优化调度，或增强故障与奖励的可观测性。
- **扩展智能体学习：** 贡献 agent loop、reward adapter、训练方案，或预算和划分清晰的评测。

欢迎[提交 Issue](https://github.com/Gen-Verse/ScienceInfra/issues) 描述使用场景与预期行为，或[提交 PR](https://github.com/Gen-Verse/ScienceInfra/pulls)。新环境请附 oracle/nop 检查结果。学习相关改动请说明奖励定义、任务划分与执行配置。

## 技术文档

以下模块指南目前为英文。

| 路径 | 内容 |
|---|---|
| [`scienceinfra/rl/`](scienceinfra/rl/README.md) | Agent loop、执行器、奖励、故障处理与 RL 方案 |
| [`scienceinfra/datasets/`](scienceinfra/datasets/README.md) | 任务库准备与数据集构建 |
| [`scienceinfra/eval/`](scienceinfra/eval/README.md) | 基线、模型评测与输出格式 |
| [`scienceinfra/configs/`](scienceinfra/configs/) | Agent 配置、容器配置与 chat template |
| [`scienceinfra/plotting/`](scienceinfra/plotting/) | 根据仓库内数据表生成图表 |
| [`scripts/`](scripts/) | 准备、训练、评测与缓存预热脚本 |

<details>
<summary><strong>排障与运行注意事项</strong></summary>

- **在 HTTP 代理后面，需要为 builder 单独配置代理，而不只是 shell。** BuildKit 不会继承 shell 的代理变量，因此第一个任务镜像会在 `apt-get install` 处静默卡住，直到构建超时。请在 `~/.docker/config.json` 中加入 `proxies` 配置，并先确认构建能访问网络，再去排查任务本身：
  ```bash
  printf 'FROM debian:bookworm-slim\nRUN apt-get update && echo APT_OK\n' > /tmp/px/Dockerfile
  docker build --progress=plain -t px /tmp/px | grep APT_OK
  ```
  也可以改用本地 Debian 镜像源，见 `scienceinfra/configs/apt-mirror-override.yaml` 与 `to_harbor.py --apt-mirror`。
- **启动前检查 Docker 健康状况。** 故障节点可通过 `AGENT_NODE_IPS` 排除。仅一次 `docker ps` 返回成功不足以判断守护进程健康。
- **保留任务要求的网络隔离。** 若出现 `network_mode='allowlist' is not supported`，检查 Docker 与镜像仓库可达性。将任务改为 public 网络可能让智能体获取上游答案，影响评测可信度。
- **先检查 oracle/nop。** Verifier 异常时，模型分数缺乏可解释性。
- **对齐提示设置。** `eval/unhinted.parquet` 与 `eval/L1.parquet` 测量不同任务条件，不能直接作为同条件的训练前后比较。
- **逐节点预热缓存，控制并发。** BuildKit 缓存为节点本地缓存。科学程序编译和验证本身会并行，过高并发可能引发资源竞争与超时。

更完整的 Docker 检查命令见[英文首页](README.md#documentation)，具体错误定位见各模块指南。

</details>

## 引用

使用科学环境、方法或论文实验结果时，请引用 ScienceIDE：

```bibtex
@misc{geng2026scienceide,
  title  = {{ScienceIDE}: Scaling Scientific Experience toward 1,000 Executable Environments},
  author = {Geng, Hejia and Huang, Zesen and Li, Haoyang and others},
  year   = {2026},
  url    = {https://aitonomy.org/projects/scienceide}
}
```

使用本基础设施时，也请附上 ScienceInfra 仓库链接，并记录实验使用的 commit。

## 致谢

ScienceInfra 基于 **[PSRL](https://github.com/psrl-project/psrl)**、**[veRL](https://github.com/volcengine/verl)**、**[Harbor](https://github.com/laude-institute/harbor)** 和 **[vLLM](https://github.com/vllm-project/vllm)** 构建。感谢 ScienceIDE 贡献者，以及支持这些环境的科学软件维护者。

## 许可证

ScienceInfra 以 [Apache License 2.0](LICENSE) 发布。

环境所构建和验证的科学程序属于第三方软件，各自遵循其自身的许可证。构建环境时会拉取这些上游源码，本仓库不对其重新授权。在重新分发某个环境或其构建产物之前，请先确认对应上游项目的授权条款。
