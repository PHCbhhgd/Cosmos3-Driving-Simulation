# 实测报告

记录日期：2026-11-02。固定源码、模型及锁文件哈希见 [versions.json](../configs/versions.json)。下面是原工作环境中的实际 GPU 运行证据；公开整理版的可移植脚本另外经过 CPU 检查。后者尚未完成全新机器端到端复测。

## 环境与成功结果

原宿主 Ubuntu 20.04/glibc 2.31；Auto 运行在单独准备的 Ubuntu 24.04 用户态，驱动 595.58，4×RTX 4090 24 GiB，Python 3.13/Torch 2.10/CUDA13。Nano 使用隔离 Python3.12/Torch2.13/CUDA13 流式卸载环境。未修改其他用户任务。

| 测试 | 参数 | 结果 |
| --- | --- | --- |
| Nano T2V | 848×480，121帧，24 FPS，35步，seed0，guidance6，BF16 | 完整解码通过，207.06s，PyTorch allocated 峰值 5,193,131,520 bytes |
| Transfer 直行 | 七路832×480，61帧，30 FPS，35步 | 联合采样后独立官方 VAE 解码；20 LiDAR sweeps，打包和浏览器检查通过 |
| Transfer 左横移 | 同上，输入末端 x=8m/y=1m | 同上；每 sweep 179,812–182,010 个有效点 |
| Sim-Auto | 发布配置 `multiview_maskless_kv` | 官方硬件 gate 拒绝 sm89，未执行完整生成 |

Transfer 两次均约 18 分钟采样，不含场景准备、独立解码与回放处理；没有足够重复测量把该时间作为稳定性能 benchmark。点数范围仅说明导出的有效格点数量。

## 通过检查的含义

- 视频：七路完整 FFmpeg 解码、832×480、61帧、30FPS。
- LiDAR：20×128×1800，frame IDs 0,3,…,57，range 为 0 invalid 或 5–100m，intensity 为 [0,1]，全部有限。
- 几何导出：采用 Pandar128 非均匀 beam elevations；range→XYZ 后模长往返一致，逐 sweep 输出 binary little-endian PLY XYZI。
- 浏览器：真实 Chrome 解码七路视频，时间轴跳转、点云拖动、RGB/WSM 切换、播放推进与同步误差 <120ms，无 JS errors。

这些检查证明文件和工具链可用，没有证明物理真值、感知模型收益、跨视角严格一致性或驾驶策略闭环有效。

## 几何诊断

将生成 LiDAR 与稀疏输入 HD-map 几何控制在相同 ray 上比较，见 [直行](../reports/transfer/straight/control_depth_agreement.json)／[左横移](../reports/transfer/left_shift/control_depth_agreement.json)。

| 逐扫描统计的算术平均值 | 直行 | 左横移 |
| --- | --- | --- |
| 受控射线预测有效覆盖 | 0.904169 | 0.911259 |
| 共同有效射线 range MAE | 6.7303m | 4.3494m |

覆盖率分母为有几何控制的 rays；MAE 在控制和输出都有效的 rays 上计算。左横移全部受控 rays 中约 67.83% 的距离误差 <2m。它们是诊断值，没有设合格阈值。控制本身稀疏且不包含完整世界，不等同于真实 LiDAR GT；点云未逐点去畸变。

人工抽查 0/1/2 秒七视角与 50/50 WSM 叠加图，主要车辆／路沿大体跟随控制，局部形状和位置仍偏离。两次输出的背景外观有差异，相同 seed 不保证场景身份固定。

## 失败案例也保留

1. 首次参考 61 帧联合任务：35步采样完成，模型同驻时 LiDAR VAE 解码 OOM，未保存可用传感器输出。该任务不计成功。
2. 121 帧／4 秒联合场景：第一步采样 OOM。没有完成 4 秒生成。
3. 后续 61 帧自定义场景：采样完成，模型同驻解码仍 OOM；已保存完整 joint latent，在独立进程用未改动的官方 VAE 解码后得到首页传感器结果。
4. 独立 VAE 预检：相机零 latent 与 LiDAR 控制重建通过，峰值 allocated 约5.1/13.4GiB；它们只是容量检查，不属于生成结果。
5. Sim-Auto：硬件不兼容，不绕过 gate，不报告“已跑通”。

原始大日志保留在原工作环境，没有全量提交 Git。公开 [failure-summary.json](../reports/failure-summary.json) 是人工整理的索引，需与直接导出的机器验证 JSON 区别理解。

## 输入轨迹的实际范围

完整输入含 0–4 秒轨迹，自车 x=4t，左横移在4秒内累计2米。实际只生成前61帧，0–2秒累计 x=8m、y=1m；直行 y=0。不是完整3.5米换道，也不是从生成视频中测量的自车位姿。

视频 61/30=2.0333秒的容器时长与最后采样时刻 60/30=2秒不同；LiDAR 20 sweeps 对应0–1.9秒起始时间，最后 sweep 到2秒。回放按时间戳对齐并保持最近一次扫描，不把缺少的扫描插值成新测量。

## 公开证据的可追溯性

[reports/](../reports/README.md) 的 JSON 从实际输出导出，仅替换本地绝对路径。原 bundle 的 `bundle-SHA256SUMS` 用于原始77文件产物；脱敏发布包会重新计算各自 `SHA256SUMS`，两者不能混用。仓库保留的 GIF 是从生成 MP4 下采样的展示副本；首页现以实际视频抽帧图展示各场景，SHA256 见 media manifest。版本锁定不保证不同硬件/算子之间逐字节一致。

## 公开整理版的实际检查

公开场景构造器与请求导出器已使用现有固定版本环境执行。两组新生成的轨迹 CSV 与原实测输入逐字节一致，请求和 caption JSON 内容一致；复用原有渲染控制，七路 WSM 完整解码、LiDAR 控制数值检查通过。见 [portable-input-check.json](../reports/portable-input-check.json)。这次没有重新运行 GPU renderer、模型采样，也没有新机器安装验证。
