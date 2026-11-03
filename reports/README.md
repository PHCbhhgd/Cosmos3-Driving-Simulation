# 公开证据索引

这里保留 2026-11-02 基础复现与 2026-11-03 鲁棒性测试的机器输出；文件中的本地绝对路径已替换为相对来源路径。没有改写状态、数值或通过结论。`failure-summary.json` 和 `summary.json` 是基础复现整理索引；新增测试见下方 robustness 目录。

| 位置 | 内容 |
| --- | --- |
| [summary.json](summary.json) | 成功／受阻状态和产物参数 |
| [nano/result.json](nano/result.json) | Nano 请求、耗时、PyTorch峰值与原视频哈希 |
| [nano/video_validation.json](nano/video_validation.json) | SHA256与完整视频解码 |
| [transfer/straight/](transfer/straight/) | 直行 bundle、逐扫描诊断、浏览器验证、输入轨迹 |
| [transfer/left_shift/](transfer/left_shift/) | 左横移同类证据 |
| [hardware/sim_auto.json](hardware/sim_auto.json) | 原版硬件 gate 的拒绝原因 |
| [hardware/isolated_vae_preflight.json](hardware/isolated_vae_preflight.json) | 官方 VAE 独立容量预检；非生成结果 |
| [portable-input-check.json](portable-input-check.json) | 公开场景脚本的输入等价与完整控制解码检查 |
| [release-asset.json](release-asset.json) | 本地传感器归档的大小、哈希与完整性 |
| [failure-summary.json](failure-summary.json) | 失败尝试及恢复范围 |
| [robustness/nano/](robustness/nano/) | Nano 逐次业务与时长请求、Guardrail 拒绝、完整解码诊断 |
| [robustness/transfer-business/](robustness/transfer-business/) | Transfer 各业务场景运行状态、七相机/点云检查、逐扫描控制一致性和事件细查 |
| [robustness/transfer-duration/](robustness/transfer-duration/) | 单相机 RGB 独立时长/续生成请求、完整解码与对齐 WSM 抽帧；running 不算完成 |
| [robustness/business-release-asset.json](robustness/business-release-asset.json) / [校验](robustness/business-release-audit.json) | 七场景本地完整传感器归档的大小、SHA256、内部清单与元数据审计 |
| [robustness/matched-controls.json](robustness/matched-controls.json) | 晴雨雪与冲突文字测试的几何、控制数组/视频一致性 |
| [robustness/lidar-boundaries.json](robustness/lidar-boundaries.json) | 官方 LiDAR 表示 5–100 m 与 validity 边界；不含生成模型运行 |
| [robustness/sim-hardware.json](robustness/sim-hardware.json) | Sim 官方 sm89 硬件拒绝；没有生成视频 |
| [robustness/visual-observations.json](robustness/visual-observations.json) | 人工抽帧的具体缺陷、时间戳与结论范围 |

`bundle_manifest.json` 的 passed 仅对应格式、解码、数值和导出检查；物理质量没有通过结论。`input_trajectory.csv` 包含4秒多一点的输入位姿，但生成输出仅覆盖前2秒。

`bundle-SHA256SUMS` 对应原始工作目录的完整 bundle，文件可能未包含在 Git 中。本地脱敏归档里的 metadata 会脱敏并重新生成 `SHA256SUMS`；使用归档自身清单校验。

目录存在或状态为 running 均不算完成；generated_and_packaged 也只说明生成、打包与记录中的检查完成。质量观察和复跑方式见 [业务场景与边界测试](../docs/ROBUSTNESS_TESTS.md)。
