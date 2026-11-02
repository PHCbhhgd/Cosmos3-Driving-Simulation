# 已知问题与排查

| 现象 | 本次发现 | 处理方向 |
| --- | --- | --- |
| Ubuntu20 导入依赖失败、GLIBC 符号不足 | host glibc2.31 不满足上游运行库 | 在兼容原生 OS／管理员提供的容器运行；不替换宿主 glibc |
| 61帧采样完成后 LiDAR decode OOM | denoiser 与 VAE 同驻占用过高 | 应用两文件补丁保存 latent，独立进程顺序官方 VAE 解码 |
| 121帧第一步 OOM | 采样本身放不下 | 退回已验证61帧；分离解码不能解决采样 OOM |
| Sim-Auto sm89 gate 拒绝 | rolling `multiview_maskless_kv` 要求特定 FlashAttention-4 支持 | 使用官方支持 Hopper／Blackwell；不解除 gate 冒充兼容 |
| NCCL 卡住／初始化失败 | 用户态隔离中的 P2P、cuMem host 有环境差异 | 在已分配 GPU 上运行 nccl_preflight；按需 namespace profile |
| HF `socks://` unknown scheme | 客户端不识别该 proxy scheme | 检查当前终端代理与客户端 socks 支持，修正为其支持的地址；不要改共享服务器全局设置 |
| HF 浏览器成功但 token 无效 | 设备登录结果与实际授权/endpoint 不一致，需进一步诊断 | 用同一个 HF_HOME/endpoint 执行 `hf auth whoami`；确认模型权限；不在 issue 中粘贴 token |
| 7路视频浏览器不可跳转 | 普通 HTTP 服务缺 byte ranges | 使用本仓库 serve_replay.py，CPU 测试覆盖范围请求 |
| Chromium 缺依赖／可执行文件 | Playwright browser 尚未准备 | 安装 chromium，或 COSMOS3_BROWSER 指向现有兼容浏览器；系统依赖由管理员提供 |
| request存在但实际帧数不对 | caption chunk span 会参与时长决定 | 使用 export_scene_request.py，同步61帧与 `[0,64)` caption chunk |

网络错误需要根据当前终端配置诊断；本仓库脚本不设置/清空代理、不强制 Hugging Face endpoint。不要通过修改全局网络配置来解决单个模型下载问题。

手动通信预检仅在已获分配的 GPU 上运行：

```bash
COSMOS3_GPUS=0,1,2,3 bash scripts/run_env.sh   storage/venvs/auto/bin/torchrun --standalone --nproc-per-node=4 scripts/nccl_preflight.py
```

补丁的两个改动：暴露已有 raw-pixel 内存优化 schema；在解码前保存联合 latent 和解析参数。没有修改权重、采样数学或 attention 硬件选择。上游更新后不能盲目套 patch，应重新固定源码、验证差异与结果。
