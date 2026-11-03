# GitHub 发布

已发布仓库：[PHCbhhgd/Cosmos3-Driving-Simulation](https://github.com/PHCbhhgd/Cosmos3-Driving-Simulation)。
传感器附件：[v0.1.0 Release](https://github.com/PHCbhhgd/Cosmos3-Driving-Simulation/releases/tag/v0.1.0)。以下步骤用于维护和后续发布。

## 发布内容

Git 仓库包括原创脚本／文档、上游补丁、小型演示和脱敏证据。模型权重、用户登录凭据、第三方 checkout、venv、rootfs、大日志和完整传感器数据均不提交。数据包通过 GitHub Release 附件发布。

当前仓库名建议 `Cosmos3-Driving-Simulation`；账号由发布者选择。发布前需要发布者已登录 GitHub，并配置自己认可的 Git 提交身份。工具不会推断用户账号，也不会把 Hugging Face 登录当作 GitHub 登录。

## 本地检查

```bash
python3 -m unittest discover -s tests -v
python3 scripts/audit_public_repo.py
ruff check scripts tests
ruff format --check scripts tests
```

`reports/publication-validation.json` 记录本次整理验证；GitHub Actions 只验证 CPU 工具链，不跑 GPU 模型。

## 创建仓库并 push

需要 GitHub CLI `gh`（可由管理员安装，也可放入个人工具目录），登录并在当前仓库配置作者。当前整理机器已在忽略目录 `storage/bin/gh` 准备校验过的 CLI，可先执行 `export PATH="$PWD/storage/bin:$PATH"`：

```bash
gh auth login --hostname github.com --web
# 使用自己的真实/公开提交身份；邮箱可用 GitHub noreply 地址
git config user.name '<提交者姓名>'
git config user.email '<GitHub邮箱或noreply地址>'
# 该命令检查、提交并创建公开仓库；账号/仓库名由自己填写
bash scripts/publish_github.sh <owner>/Cosmos3-Driving-Simulation
```

脚本先检查目标仓库不存在；如果已有 origin、已有同名仓库或认证/权限不足会退出。已有仓库的维护需单独审查 remote 后操作，不覆盖他人的历史。

## 构建完整传感器附件

```bash
python3 scripts/build_release.py   --straight /path/to/straight-bundle   --left-shift /path/to/left-shift-bundle   --comparison media/trajectory-comparison.mp4   --redact-root /path/to/original-reproduction   --output release
```

构建器验证源 bundle SHA256，拒绝 symlink 和非预期文件类型，复制传感器输出并替换 JSON 中的原始服务器绝对路径，为两个新 bundle 重新生成校验清单，再生成 `.tar.gz` 与 SHA256 sidecar。包含七路 RGB/WSM、原生 LiDAR、40份 PLY（每场景20份）、标定、输入位姿、viewer 和评阅素材；不包含模型权重。

本次整理若已有 `release/cosmos3-trajectory-sensors.tar.gz`，可直接使用，先核对同目录 SHA256。对外发布前查看其中 README 的范围说明。

```bash
gh release create v0.1.0   release/cosmos3-trajectory-sensors.tar.gz   release/cosmos3-trajectory-sensors.tar.gz.sha256   --title 'Cosmos3 trajectory-conditioned RGB + LiDAR reproduction'   --notes-file docs/RELEASE_NOTES.md
```

仓库公开成功和 Release 上传是两个步骤，只有命令实际成功后才应在 README 填写在线链接。

## 业务与时长附件

七个联合场景的附件构建方式：

```bash
python scripts/build_robustness_release.py outputs/robustness/<业务suite> \
  --output release/v0.2.0 --source-root /path/to/reproduction-parent
python scripts/audit_release_archive.py release/v0.2.0/cosmos3-business-sensors.tar.gz
```

单相机时长附件使用 `build_duration_release.py`，提供 `--scene`、`--output` 和 `--source-root`；只有四档请求均为终态才构建，不把请求帧数当作实际输出帧数。`--cases` 和 `--archive-name` 可用于独立的单场景补测。构建时保留失败记录，已生成的 MP4 字节保持原样，JSON 路径脱敏后重新生成 SHA256。

`audit_release_archive.py` 流式读取压缩包，不解压到文件系统，核对所有 bundle/时长清单、JSON 中的本地路径和凭据格式。该检查只证明分发完整性，不评价模型画面或传感器物理质量。公开预览由 `export_business_previews.py` / `export_duration_previews.py` 降码率导出；帧数、尺寸、FPS 和源视频 SHA256 另行记录。
