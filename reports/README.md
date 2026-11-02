# 公开证据索引

这里保留2026-11-02实际复现的机器输出；文件中的本地绝对路径已替换为相对来源路径。没有改写状态、数值或通过结论。`failure-summary.json` 和 `summary.json` 是整理索引。

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
| [release-asset.json](release-asset.json) | 本地传感器发布附件的大小、哈希与完整性 |
| [failure-summary.json](failure-summary.json) | 失败尝试及恢复范围 |

`bundle_manifest.json` 的 passed 仅对应格式、解码、数值和导出检查；物理质量没有通过结论。`input_trajectory.csv` 包含4秒多一点的输入位姿，但生成输出仅覆盖前2秒。

`bundle-SHA256SUMS` 对应原始工作目录的完整 bundle，文件可能未包含在 Git 中。公开发布包里的 metadata 会脱敏并重新生成 `SHA256SUMS`；使用发布包自身清单校验。
