# ComfyUI Soda H3 Tools

为 MiniMax H3 分段视频工作流提供项目与段号管理、续段解码、单段保存及三段音视频合并。

这是独立的社区辅助插件。它不提供模型、提示词生成服务或视频采样器，也不保证提速或提高画质。安装后仍需搭配兼容的 H3 生成工作流。

## 主要节点

在节点搜索中输入 `Soda H3`，或查找 `Soda/H3` 分类。

| 界面名称 | 功能 |
| --- | --- |
| **Soda H3 · 项目与段号** | 根据项目、段号和放大开关计算读写路径；检查前段记录、输出尺寸及 latent 文件状态 |
| **Soda H3 · 保存本段与合片** | 保存带音频的本段视频和完成记录；第 3 段保存后合并前三段 |
| **Soda H3 · 放大续段适配** | 拆分并解码上一段 H3 音视频 latent；第 1 段没有前段时返回空上下文 |

插件也保留早期项目控制、三段分镜、日常控制及保存节点，供旧工作流加载。新工作流主要使用上面三个节点。

## 安装

需要支持 MiniMax H3 及原生 VIDEO 保存接口的 ComfyUI。已验证环境为 Windows、ComfyUI 0.38.0、Python 3.13；未验证所有版本或平台。

在 `ComfyUI/custom_nodes` 中执行：

```shell
git clone https://github.com/cOkieeman/ComfyUI-Soda-H3-Tools.git
```

三段合片使用 `imageio-ffmpeg`。请用 **ComfyUI 实际运行的 Python** 安装依赖，例如 Windows 便携版根目录：

```powershell
.\python_embeded\python.exe -m pip install -r .\ComfyUI\custom_nodes\ComfyUI-Soda-H3-Tools\requirements.txt
```

重启 ComfyUI。已有同名文件夹时，先在 ComfyUI 停止后备份并替换原插件；不要把同一插件以两个文件夹同时放在 `custom_nodes` 中。通过 Git 安装后可在插件目录用 `git pull --ff-only` 更新。

续段读写需另外安装 [ComfyUI H3 Motion Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)。潜空间放大、模型与采样节点由所用工作流自行提供，本插件不会自动安装或下载。

## 接线说明

“项目与段号”的 `width`、`height` 接生成尺寸；`upscale_mp` 接放大目标 MP。即使关闭放大，这三个必填输入也需要连线。开启放大时，目标尺寸按 `MP × 1024²` 和 32 像素倍数计算，工作流放大节点必须使用相同规则。

| 输出 | 接到哪里 |
| --- | --- |
| 本段 | Motion Context Save Latent 的 `clip_index` |
| 上一段 | Motion Context Load Latent 的 `clip_index` |
| 读取目录 | Load Latent 的 `latent_path` |
| 保存前缀 | Save Latent 的 `filename_prefix` |
| 启用放大 | 工作流的惰性分支开关；本节点不会自行禁用采样分支 |
| 保存信息 | “保存本段与合片”的 `receipt` |

将 Save Latent 输出的文件路径接到“保存本段与合片”的 `latent_path`，将裁切重叠后创建的原生 VIDEO 接到 `video`。保存节点不执行重叠裁切或重新采样。

开启两次采样的潜空间放大时，可把 Load Latent 输出接到“放大续段适配”，并接视频 VAE 与音频 VAE。该节点输出画面和声音，供低分辨率 Motion Context 使用；高分辨率续段可按工作流直接使用保存的 latent。原始音视频流保持原尺寸，后续缩放由工作流负责。

## 逐段操作

1. 输入新项目名，从第 1 段开始，设置参考素材与本段提示词后运行。
2. 检查视频；保持项目名、尺寸和放大开关不变，改成第 2 段并填写下一段正文。
3. 第 3 段同样操作，完成后会保存本段和完整三段视频。

不要在前段完成前排后段。同一个项目不要并行生成，否则固定 latent 槽位可能互相覆盖。重做第 1 段后，需要依次重做后续段。更换模型、LoRA 或从头尝试时请使用新项目名；这些更改不会被节点自动全面检测。

只在保存第 3 段时自动合并前三段；第 4 段及以后单独保存，不自动合成长片。

## 文件与兼容性

主要节点使用以下相对于 `ComfyUI/output` 的目录：

```text
h3_context/teacher/<项目>/<standard 或 upscale>/clip_00001.safetensors
h3_context/teacher/<项目>/<standard 或 upscale>/clip_00001.soda.json
MiniMax_H3/teacher/<项目>/<standard 或 upscale>/
```

视频按保存次数保留；latent 使用固定段号槽位。`.soda.json` 是续段完成记录，需要与视频及 latent 一起保留。合并采用 FFmpeg 流复制，输入片段应具有一致的尺寸、帧率和音轨配置。

**旧内部 ID `SodaH3TeacherControl`、`SodaH3TeacherSave`，模块名 `teacher.py` 及路径中的 `teacher` 保留作兼容用途。** 改掉它们会影响旧工作流加载或旧项目续段。仓库名与界面显示名使用 Soda H3，不需要用户迁移已有工作流。

本插件不主动联网、不需要 API 密钥。原生视频保存时会附带 ComfyUI 提供的 prompt 和工作流元数据；分享生成文件前请留意其中的提示词与路径信息。

## 测试与验证范围

不加载模型、不启动 ComfyUI 的测试：

```shell
python -m unittest discover -s tests -v
```

测试覆盖插件注册、旧类型兼容、前段缺失与重做检查、文件状态检查、尺寸/模式隔离，以及 list/tuple/nested 音视频 latent 拆分。解码测试使用替身，不代替 GPU 实跑。

2026-10-01 在 RTX 5060 Ti 16GB 上，配套工作流实跑过普通三段及音视频合片，以及放大首段和第二段：目标每段 5 秒，普通 544×800，放大至 640×960。更高分辨率、长片、放大第三段及任意第三方工作流未在此验证。公开发布整理不改变采样行为。

## 许可证

本仓库原创辅助代码采用 MIT 许可证。模型、ComfyUI 和其他节点包分别遵守各自的许可证。
