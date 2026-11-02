# 复现指南

## 1. 环境范围

主线是 Transfer-Auto 联合 RGB/LiDAR 的低显存推理。源码和模型 revision 固定在 [versions.json](../configs/versions.json)。Auto 保留上游 `uv.lock`，使用 Python 3.13、`cu130-train`、`train` 和 `guardrail` extras；Nano 单独使用 Python 3.12 + streaming adapter，Diffusers 固定到已用的提交。

建议 Linux x86-64、Ubuntu 24.04、glibc ≥2.35、CUDA 13 兼容驱动与可用 CUDA 工具链。上游建议约 150 GiB 起步，本项目若保存多个模型、两套环境、场景、latent 和完整 bundle，应再预留空间。Nano 流式卸载也需要充足主存；这里没有测量最低主存门槛。

管理员提供的系统依赖示例（**由管理员评估并执行**）：

```bash
apt-get install python3-venv git git-lfs ffmpeg build-essential gcc-13 g++-13   libgl1 libegl1 libglib2.0-0 libx11-dev libegl1-mesa-dev libgl1-mesa-dev
```

CUDA 工具链和驱动需按服务器实际版本配置。本仓库不执行 sudo、不修改 Docker 用户组、系统 glibc、全局代理或现有 conda 环境。

历史测试的宿主机是 Ubuntu 20.04/glibc 2.31，使用已单独配置的 Ubuntu 24.04 `bwrap` 用户态运行。**该 rootfs 不随公开仓库提供，也没有自动安装脚本**。本仓库 `ubuntu_env.sh` 只是原接口的透传入口；在兼容原生系统或管理员配置的容器内执行下述命令。不要在 Ubuntu 20.04 宿主直接套用后声称环境相同。

## 2. 获取源码并建立环境

下载或 clone 本仓库后进入根目录：

```bash
bash scripts/bootstrap.sh
bash scripts/run_env.sh bash scripts/install_auto.sh
bash scripts/run_env.sh bash scripts/install_wsm.sh
storage/venvs/review/bin/python -m playwright install chromium
```

`bootstrap.sh` 仅在项目目录安装 uv 0.11.29，clone 固定 Framework 提交，校验锁文件与补丁哈希，应用补丁，并只拉取 WSM 路径的 Git LFS 资源。已有 checkout 若提交不一致会退出，不 reset。仅复现 Nano 时可加 `--skip-lfs`。

若编译需要指定 GCC：在 `run_env.sh` 命令前设置 `CC=/usr/bin/gcc-13 CXX=/usr/bin/g++-13`。依赖安装中任何错误都应先解决；不要用无关版本的 attention 包覆盖上游锁文件。

## 3. 授权与下载

在 Hugging Face 先接受计划使用的 Cosmos3 模型和 `nvidia/Cosmos-Guardrail1` 的访问条款，并确认账号已有权限。

```bash
bash scripts/run_env.sh storage/venvs/framework-hf-cli/bin/hf auth login
bash scripts/run_env.sh storage/venvs/auto/bin/python scripts/download_models.py transfer
bash scripts/run_env.sh storage/venvs/auto/bin/python scripts/download_framework_guardrails.py
```

脚本使用正常 Hugging Face 凭据和固定 revision，保留既有 `HF_HOME`、`HF_TOKEN_PATH`、`HF_ENDPOINT` 和代理设置。默认沿用用户自己的 HF cache。不要把 token 写到受 Git 跟踪的文件中。需要自定义 cache 时，在**登录和下载前**统一设置 `HF_HOME`；已在其他 token 路径登录可显式传 `HF_TOKEN_PATH`。下载器完整获取模型 snapshot，避免遗漏根目录的模型分片。

原版参考场景（可选，完整规格未在本次机器跑通）：

```bash
bash scripts/run_env.sh storage/venvs/auto/bin/python scripts/download_models.py sample
COSMOS3_GPUS=0,1,2,3 bash scripts/launch_auto.sh transfer reference
```

该命令按上游完整 720p 请求运行，不能用它代表本项目已验证的 61 帧规格。

## 4. 准备合成场景

```bash
export COSMOS3_GPUS=0,1,2,3  # 替换为自己获分配的空闲 GPU
bash scripts/run_env.sh bash scripts/prepare_scene.sh straight
bash scripts/run_env.sh bash scripts/prepare_scene.sh lane_change
```

每个场景先创建 121 帧、30 FPS 的 4 秒控制，额外三帧位姿支持扫描末端插值。直行自车 x=4t，y=0；左横移为 y=2(10u³−15u⁴+6u⁵)，u=t/4，并按速度方向设置 yaw。前车 x=24+3t，另有右侧停放车、车道线、路沿、灯杆。

相机采用上游 Hyperion8 参考标定中的七路身份；LiDAR mount `[1.1,0,1.9]` 米为显式合成值。WSM4 相机控制渲染到 1280×720；LiDAR 几何控制渲染 41 次扫描。`export_scene_request.py --frames 61` 完整解码检查输入，再生成 `request-joint-61.json` 和 `[0,64)` caption chunk。它选择前 61 帧，**不把整个 4 秒轨迹压缩为 2 秒**。

已有场景会保留并退出；需要变更输入时先备份旧目录。输入预览或 VAE reconstruction 不能当作模型生成视频。

## 5. 推理、解码与打包

```bash
COSMOS3_GPUS=0,1,2,3 bash scripts/run_scene_pipeline.sh straight
COSMOS3_GPUS=0,1,2,3 bash scripts/run_scene_pipeline.sh lane_change
```

每次任务先用 `nvidia-smi` 检查四张卡：无计算进程、已用显存 <1024 MiB、利用率 ≤5%。检查只是启动前快照，不是 GPU 预约锁；共享服务器仍需遵守调度分配。任何已有计算进程都会使入口退出。脚本不 kill 任务，也不自动选择别人的 GPU。

配置：480p、832×480、61 帧、30 FPS、seed 0、35 步、guidance 3、shift 10、CP=4、CFGP=1、DP shard=4、上游逐视角 negative prompt、关闭 compile/diffusion cache，开启 guardrail offload。

补丁暴露上游已实现的 raw-pixel CPU 内存优化，并在 VAE 解码前保存 joint latent。主任务若失败，仅当两份完整 latent 文件存在时才尝试独立解码；采样 OOM 不会被转换为成功。解码器依次加载原版相机 VAE 与 FP32 LiDAR VAE，使用原模型投影/分块配置，不重复采样。日志全部保存在本地 `artifacts/`。

旧用户态中测过的 NCCL 兼容配置可按需启用：

```bash
COSMOS3_NCCL_PROFILE=namespace COSMOS3_GPUS=0,1,2,3   bash scripts/run_scene_pipeline.sh lane_change
```

它仅对子进程设置 SHM=0、P2P_DISABLE=1、CUMEM_HOST_ENABLE=0。原生环境默认保留 NCCL 自身选择。完成下载后可自行增加 `HF_HUB_OFFLINE=1`。

单独恢复与打包：

```bash
export SAMPLE="$PWD/outputs/<run>/<sample>"
export BUNDLE="$PWD/outputs/bundles/<新名称>"
COSMOS3_GPUS=0 bash scripts/run_env.sh storage/venvs/auto/bin/python   scripts/decode_joint_latents.py "$SAMPLE"
COSMOS3_GPUS=-1 bash scripts/run_env.sh storage/venvs/auto/bin/python   scripts/package_simulation.py "$SAMPLE"   --request storage/scenarios/lane_change/request-joint-61.json   --scene storage/scenarios/lane_change --output "$BUNDLE"
storage/venvs/review/bin/python scripts/review_sensor_bundle.py "$BUNDLE"
storage/venvs/review/bin/python scripts/evaluate_joint_controls.py "$BUNDLE"   --scene storage/scenarios/lane_change
storage/venvs/review/bin/python scripts/check_replay_browser.py "$BUNDLE"   --report artifacts/replay-validation.json
python3 scripts/serve_replay.py "$BUNDLE" --port 8080
```

独立解码命令应在确认该单卡已空闲后使用。浏览器默认使用 Playwright Chromium；可通过 `COSMOS3_BROWSER` 指定兼容 Chrome/Chromium。只运行在回环地址，服务器远程访问用 SSH 端口转发。

## 6. Nano 单卡复现

```bash
bash scripts/run_env.sh bash scripts/install_nano.sh
bash scripts/run_env.sh storage/venvs/cosmos3/bin/python scripts/download_models.py nano
COSMOS3_GPUS=0 bash scripts/nano_env.sh storage/venvs/cosmos3/bin/python   scripts/nano_smoke.py --frames 121 --steps 35 --height 480 --width 848 --seed 0
python3 scripts/validate_nano_output.py outputs/<nano-run>
```

默认脚本参数为 17 帧／4 步的连通测试；上面显式参数才对应首页展示的结果。默认安全检查保持开启。Nano 不使用四卡的 `launch_auto.sh`，单卡运行前需自行检查 GPU 占用。

## 7. Sim-Auto 的当前终点

```bash
bash scripts/run_env.sh storage/venvs/auto/bin/python scripts/download_models.py sim
COSMOS3_GPUS=0 bash scripts/run_env.sh storage/venvs/auto/bin/python   scripts/check_sim_hardware.py
```

硬件不支持时返回非零退出码，报告落在 `artifacts/sim_hardware_check.json`。4090/sm89 被当前官方 FlashAttention-4 rolling gate 拒绝。应在官方支持的 Hopper/sm90 或受支持 Blackwell/sm100/sm103 上继续验证；换卡后仍需检查依赖与显存，不能仅凭架构宣称跑通。Sim 的固定四步／因果滚动配置不能直接复用 teacher 的 35 步请求。完整运行请从固定 Framework 提交的 Sim-Auto inference guide 与官方样例开始。

## 8. CPU 与公开文件检查

```bash
python3 -m unittest discover -s tests -v
python3 scripts/audit_public_repo.py
ruff check scripts tests
ruff format --check scripts tests
```

GitHub Actions 仅运行 CPU 工具测试、证据一致性、公开文件审计与语法／格式检查。新公开脚本与历史 GPU 运行应分别理解；本次未从空机器重新下载全部权重并重复推理。
