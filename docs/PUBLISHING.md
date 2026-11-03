# GitHub 内容与本地数据

公开仓库：[PHCbhhgd/Cosmos3-Driving-Simulation](https://github.com/PHCbhhgd/Cosmos3-Driving-Simulation)。

## 发布规则

GitHub 只保存原创代码、文档、配置、上游补丁、脱敏报告、场景图片与小视频。**大文件保留在本地，不提交 Git，也不上传 GitHub Release。** 完整传感器归档、模型权重、第三方 checkout、venv、rootfs 和原始长视频均属于本地内容。

公开目录执行每个文件 **10 MiB** 的大小上限检查；场景在 README 使用一张代表性实测图片，已有小视频保留链接。该上限是本仓库维护规则，不是 GitHub 平台限制。`outputs/`、`release/`、`storage/`、`repos/` 和 `artifacts/` 已被 Git 忽略。

原先上传的 v0.1.0 约 287 MiB 传感器附件，以及 v0.2.0 草稿约 1.09 GiB 业务附件，已从 GitHub 撤下；本地文件与 SHA256 校验文件保留。Release 可用于版本说明，不附带这些大型数据。

## 提交前检查

```bash
python3 -m unittest discover -s tests -v
python3 scripts/audit_public_repo.py
ruff check scripts tests
ruff format --check scripts tests
```

`audit_public_repo.py` 检查文件大小、被追踪的运行数据、本地绝对路径、凭据格式与文档链接。GitHub Actions 只验证 CPU 工具链，不跑 GPU 模型。

已有仓库维护时，审查 `git diff` 和 `git status` 后正常提交、push；不要把被忽略的运行目录强制加入 Git。`publish_github.sh` 用于首次创建新仓库，已有 origin 或目标仓库时会退出。

## 场景图片与小视频

```bash
python scripts/export_readme_gallery.py outputs/robustness/<业务suite> --output media/scenarios-new
```

该工具从实际验证过的视频抽帧，记录源视频哈希、帧号和图片哈希；输出目录必须是新目录。README 图片不经过图像生成模型加工。

`export_business_previews.py` 可以导出保留原尺寸、FPS 的小型 H264 预览，并记录源视频和预览哈希。原始七相机/LiDAR 数据留在本地 bundle。长时序原视频优先只放代表性图片与诊断 JSON；如导出小预览，提交前同样执行大小检查。

## 本地完整归档

这些命令只构建本地备份，不执行 GitHub 上传。

基础直行/左横移：

```bash
python scripts/build_release.py \
  --straight /path/to/straight-bundle --left-shift /path/to/left-shift-bundle \
  --comparison media/trajectory-comparison.mp4 \
  --redact-root /path/to/reproduction-parent --output release
```

七个联合业务场景：

```bash
python scripts/build_robustness_release.py outputs/robustness/<业务suite> \
  --output release/v0.2.0 --source-root /path/to/reproduction-parent
python scripts/audit_release_archive.py release/v0.2.0/cosmos3-business-sensors.tar.gz
```

单相机时长与补测：

```bash
python scripts/build_duration_release.py outputs/robustness/<时长suite> \
  --scene storage/scenarios/temporal_following \
  --output release/v0.2.0 --source-root /path/to/reproduction-parent
```

时长构建器要求四档请求均为终态，保留失败记录；`--cases`、`--archive-name` 用于独立补测。构建器验证源数据并替换 JSON 中的服务器路径，MP4 原始字节保留，归档内重新生成 SHA256。`audit_release_archive.py` 流式核对压缩包清单与 JSON 元数据，不评价画面或传感器物理质量。

回放本地 bundle：

```bash
python scripts/serve_replay.py outputs/robustness/<业务suite>/clear_turn/bundle --port 8080
```

打开 `http://127.0.0.1:8080`，可切换 RGB/WSM、同步播放和旋转点云。
