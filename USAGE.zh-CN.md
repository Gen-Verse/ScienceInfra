# ScienceInfra 使用指南

[返回首页](README.zh-CN.md) · [English](USAGE.md)

## 架构

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

该命令把编写好的任务编译为 Harbor 任务，并把 Parquet 写入 `data/laps/repair_easy/`。若要使用 MITgcm demo，先按 [`demo/README.md`](demo/README.md) 恢复其二进制输入，再改用 `--envs mitgcm-biogeo`。

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

## 排障

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

更完整的 Docker 检查命令见[英文首页](USAGE.md#troubleshooting)，具体错误定位见各模块指南。

</details>

