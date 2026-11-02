# 输入、输出和仿真范围

## 三类模型

基础 Nano 是通用多模态世界模型；本项目仅验证文本生成单路视频。Transfer-Auto 是使用多摄像头场景控制的驾驶模型，本次验证联合 RGB/LiDAR。Sim-Auto 是因果、蒸馏、滚动驾驶生成路径，当前硬件测试没有完成生成。不要把基础 Nano 的单视频能力等同多摄像头驾驶仿真。

## 本项目 Transfer-Auto 输入

- 自车／前车逐帧位姿、静态停放车辆与道路几何。
- Hyperion8 参考 rig 中的七个物理相机身份：front_wide、cross_left、cross_right、rear_left、rear_right、rear_tele、front_tele；精确 key 在 scene manifest。
- 各相机 WSM4 视频与 camera-local caption sidecar，输入控制30FPS。
- Pandar128 range 几何控制和显式合成 LiDAR mount。
- 原生 JSON 请求：text2video、seed0、guidance3、shift10、61帧。本测试无真实初始 RGB，不需要提供实车录制视频。

WSM 表示场景语义／几何控制，不是生成 RGB 的替代品。输入 trajectory/pose 来自场景构造器，不是模型新预测的轨迹。

## 已导出的输出

```text
bundle/
  cameras/<camera_key>.mp4      七路 RGB，832×480，61帧/30FPS
  controls/<camera_key>.mp4     对齐后的输入控制预览
  lidar.safetensors            range_m/intensity/frame_ids
  pointclouds/<frame_id>.ply    binary little-endian XYZI
  lidar_calibration.json       模型 range projection 和非均匀 elevations
  camera_calibration.json      上游参考原生 FTheta 标定
  camera_image_geometry.json   控制裁切/缩放与输出像素坐标变换
  trajectory.{csv,npz}          输入位姿；不当作模型估计
  synchronized_frames.csv      按时间戳对应的相机、最近 LiDAR 和输入 pose
  scenario_inputs/             紧凑的合成道路／参与者输入与 captions
  bundle_manifest.json         完整解码、数值与导出检查
  SHA256SUMS                   当前 bundle 文件校验清单
  index.html / serve_replay.py  同步交互回放
  review/                      实际视频拼图、抽帧与诊断
```

LiDAR semantic shape 为20×128×1800，模型内部圆周 padding 后宽1808，原生投影宽3600。XYZ 使用 Pandar128 非均匀竖直角，不能用均匀128线假设替代。点云坐标为传感器 FLU（x前/y左/z上），单位米；给出 sweep 起止变换，但未按点时间去运动畸变。

相机标定和像素 affine 描述控制几何，不能认为生成 RGB 已满足实测相机的严格标定精度。LiDAR intensity 是模型生成量；没有传感器噪声／反射物理标定验证。

## 与“完整闭环仿真”的距离

当前完成“轨迹输入、RGB+LiDAR生成、点云导出、同步查看”的开环链路。驾驶策略不读取生成传感器来更新自车轨迹；没有车辆动力学、碰撞反馈或闭环任务成功率，也没有 Radar/IMU/GNSS。若接入 AlpaSim 等闭环系统，还需对接传感器/动作/时间接口，并验证闭环数值稳定性与策略指标。

Cosmos Dataset Search 和 Cosmos-Curate 属于真实数据检索／整理环节，可为场景选择与条件构造提供数据；它们不是本仓库的传感器生成模型。本仓库暂未接入这两个平台。
