# 业务场景与边界测试

本轮测试区分三个问题：能否生成并完整解码；是否遵循轨迹、天气与事件要求；同一段连续视频中，何时首次出现可观察的退化。文件检查通过不代表后两项通过。

## 测试设计

模型、Framework、VAE 与低显存补丁沿用 [固定版本](../configs/versions.json)。模型权重不修改，安全检查保留。Nano 使用官方流式卸载、848×480、24 FPS、35 步、guidance 6；Transfer 使用四卡 CP4 / DP-shard4、480p、35 步、guidance 3、shift 10、官方逐视角 negative prompt。该配置下实际相机输出为 832×480。

### 七相机 + LiDAR 业务场景

[场景定义](../configs/robustness-cases.json) 与 [场景构造器](../scripts/prepare_business_scene.py) 给出可检查的几何和参与者轨迹。每例 61 帧 / 30 FPS，最后相机采样时刻 2 秒；联合输出预期为 20 次 / 10 Hz 的 LiDAR 扫描。这些是业务情形的**合成测试**，没有使用对应的实车录像作为真值。

| 场景 | 固定的输入 | 重点检查 |
| --- | --- | --- |
| 晴天左转 | 6 m/s、半径 22 m 的左弯，前车、车道与路沿 | 晴天基线、转向透视、前车身份 |
| 大雨左转 | 与晴天相同的几何和 seed，只改变天气 caption | 可见雨丝、湿路与喷雾；天气能否贯穿各视角 |
| 降雪左转 | 同上，只改变为降雪和积雪 caption | 是否生成降雪；车道、前车是否被雪覆盖或消失 |
| 鬼探头 | 路右货车遮挡行人，行人从右向左冲刺横穿 | 遮挡前不能提前出现、出现后不能消失；外观与 LiDAR 支持 |
| 邻车事故 | 左侧车辆以 5 m/s 接近停止车辆，1.1 秒发生预设 box 接触，随后轻微偏航 | 是否真正表现接触和减速，车辆是否融合、换身份或穿插 |
| 隧道入口 | 从后轴 x=0 行驶到 x=8 m，入口 x=4 m | 是否从室外进入有顶空间；墙顶、照明与曝光是否持续 |
| 控制冲突 | 几何保持左弯，文字明确要求右转 | 遵循哪种控制，有无画面撕裂或控制失效 |

左弯的短联合样本覆盖约 **31.3°**，不是完整 90° 转弯。行人从 t=0.4–1.6 秒横移 6 m，平滑轨迹峰值 7.5 m/s，属于快速冲刺压力测试。相机 WSM 已检查开头遮挡、约 1 秒时行人显露。车辆接触由轨迹直接指定，没有碰撞动力学、车身形变或碎片。隧道仅提供入口、屋顶边缘与每隔 4 m 的线框结构，**没有密集墙面和屋顶网格**。

雨、雪不会改变输入的道路几何或引入经过验证的 LiDAR 雨雪散射。几何控制第二通道为占用占位值，不是实测反射率。生成的 LiDAR 强度及天气变化不能据此解释成真实传感器物理。

### 时长与运动测试

| 模型 / 路径 | 请求 | 可以回答的问题 |
| --- | --- | --- |
| Nano / 固定路边相机文字 | 独立 121、241、397 帧，即最后采样时刻 5、10、16.5 秒 | 不同时长的提示词遵循、背景及车辆保持情况 |
| Nano / 行驶相机文字 | 397 帧、seed1，要求持续行驶和明显视差 | 有实际运动时后段的几何与身份变化 |
| Transfer / 前广角 RGB | 独立 121、241、397 帧，最后采样时刻 4、8、13.2 秒 | 受几何控制的单视角长序列质量 |
| Transfer / 前广角 RGB 续生成 | 两个 397 帧 chunk，反馈一帧，总计 793 帧 / 30 FPS | 同一序列跨 chunk 后的连续性，最后采样时刻 26.4 秒 |
| Transfer / 联合七相机 + LiDAR | 61 帧 | 本轮业务情形下的短序列与跨传感器诊断 |
| Sim-Auto | 官方硬件检查 | 当前硬件能否运行，不能回答视频质量或滚动稳定时长 |

长 RGB 控制来自真实连续渲染的 797 帧，未降低 FPS 或重复视频。第二个 chunk 的控制从 frame 396 开始，与第一段最后一帧一致；拼接时去掉一帧反馈。原生 joint 路径只支持一个 caption chunk，因此 RGB 续生成结果**不代表七相机 + LiDAR 的同等时长能力**。

不同时长请求使用相同 seed，也不保证共享相同前缀。它们是独立采样，不能通过对比“5 秒视频”和“10 秒视频”认定某个具体秒数开始失稳。

## 如何判断退化

人工审阅分别记录：时间戳、具体可见问题、输入中是否提供了对应结构、检查的是哪些相机与帧。关注车辆/行人消失或身份变化、静态结构变形、跨 chunk 跳变、天气不遵循、几何与文字冲突。问题若从第一帧就存在，记为初始生成或条件遵循失败。

“首次观察到退化”的时间只适用于具体场景、seed、分辨率和推理配置。未观察到问题时，结论只是“在已检查的窗口未发现该问题”；无运动、弱事件或不完整控制不能用来证明长时世界稳定。单 seed 不是失败率评估。

[视频审阅工具](../scripts/review_video.py) 完整解码所有帧、计算 SHA256，并导出带时间戳的抽帧。亮度、锐度和帧间像素差仅是描述性数值，不能自动判定物理稳定性。

[LiDAR 几何诊断](../scripts/evaluate_joint_controls.py) 比较稀疏受控射线上的有效覆盖与 range 误差，没有物理精度通过阈值。[参与者支持诊断](../scripts/evaluate_actor_support.py) 统计预设 box 表面附近的生成点，使用扫描开始位姿，未 deskew；附近道路或其他物体可能造成假支持，不能当作目标检测或 RGB/LiDAR 语义一致性的证明。

CUDA OOM 单独记为该配置的容量限制。Sim 的 sm89 拒绝单独记为硬件兼容限制。这两类都不能说明“世界在某秒崩坏”。

## 复跑方式

先按 [复现指南](REPRODUCTION.md) 准备固定版本、兼容运行环境与模型，并分配四张空闲 GPU。下列 Python/命令需要在对应 WSM 或 Auto 环境中运行；共享服务器不要直接占用已有计算任务的卡。

```bash
python scripts/prepare_business_scene.py rain_turn --frames 61
python scripts/render_scene_wsm.py storage/scenarios/rain_turn --frames 61
cosmos-auto-lidar-rangemap \
  --input-root storage/scenarios/rain_turn \
  --output-root storage/scenarios/rain_turn/lidar_controls \
  --clip-id rain_turn --max-frames 21 --export-control --device cpu --no-vis
python scripts/export_scene_request.py storage/scenarios/rain_turn --frames 61
```

对其余场景重复准备步骤。[批量执行器](../scripts/benchmark_transfer.py) 接受 `--runtime`（在命令前执行的环境包装脚本）、`--python`（Auto 虚拟环境解释器）、`--gpus`、`--cases`、`--output`，自动预检 GPU，保存每例结果，并在完整 joint latent 已保存而同驻解码 OOM 时尝试独立官方 VAE 解码。输出目录必须是新目录。

```bash
python scripts/prepare_business_scene.py clear_turn --frames 797 \
  --output storage/scenarios/temporal_turn
python scripts/render_scene_wsm.py storage/scenarios/temporal_turn --frames 797
python scripts/prepare_temporal_requests.py storage/scenarios/temporal_turn
```

[RGB 时长执行器](../scripts/benchmark_transfer_rgb.py) 使用 `--scene storage/scenarios/temporal_turn` 和同样的 runtime / python / GPU 参数。Nano 的 [执行器](../scripts/benchmark_nano.py) 默认执行三档时长，也可通过 `--cases-config` 指定 [业务提示词](../configs/nano-business-cases.json) 或 [持续行驶长视频](../configs/nano-motion-duration.json)。所有安全检查保持开启。

本轮机器使用已有隔离环境。可移植源码经过 CPU 检查不等于已在一台全新机器上重新安装并跑完全部 GPU 测试。
