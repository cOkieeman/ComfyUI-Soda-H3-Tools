"""Daily H3 controls. Sampling remains in the native ComfyUI graph."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

import folder_paths


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def output_path(relative):
    root = Path(folder_paths.get_output_directory()).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("输出路径必须在 ComfyUI/output 内。")
    return path


def project_name(value):
    value = value.strip()
    if not value or len(value) > 80 or re.search(r'[<>:"/\\|?*\x00-\x1f]', value):
        raise ValueError("项目名请用中文、字母、数字、下划线，不要使用路径符号。")
    if value.endswith('.') or value in {'.', '..'} or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', value, re.I):
        raise ValueError("此项目名不能作为 Windows 文件夹名称，请换一个。")
    return value


def frame_count(seconds):
    frames = max(5, round(float(seconds) * 24))
    return frames + (5 - frames % 17) % 17


def canvas(image, megapixels):
    h, w = image.shape[1:3]
    factor = min(math.sqrt(float(megapixels) * 1_000_000 / (w * h)), 1344 / max(w, h), 768 / min(w, h))
    return max(32, int(w * factor) // 32 * 32), max(32, int(h * factor) // 32 * 32)


class SodaH3ShotPlan:
    @classmethod
    def INPUT_TYPES(cls):
        required = {"common": ("STRING", {"default": "", "multiline": True, "tooltip": "每段共用的场景、主体与风格描述。策划说明不要填在这里。"})}
        for i in range(1, 4):
            required[f"shot_{i}"] = ("STRING", {"default": "", "multiline": True, "tooltip": f"第 {i} 段实际发送给 H3 的提示词。"})
            required[f"seconds_{i}"] = ("FLOAT", {"default": 5.0, "min": 1.0, "max": 10.0, "step": 0.5, "tooltip": "目标时长；会向上对齐 H3 的 17k+5 帧规则。续段还会扣除重叠帧。"})
        return {"required": required}

    RETURN_TYPES = ("SODA_H3_PLAN",)
    RETURN_NAMES = ("三段计划",)
    FUNCTION = "build"
    CATEGORY = "Soda/H3"

    def build(self, common, **kwargs):
        return ({"common": common.strip(), "shots": [{"prompt": kwargs[f"shot_{i}"].strip(), "seconds": kwargs[f"seconds_{i}"]} for i in range(1, 4)]},)


class SodaH3Studio:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "plan": ("SODA_H3_PLAN",), "image": ("IMAGE",),
            "project": ("STRING", {"default": "我的第一条短片"}),
            "take": ("INT", {"default": 1, "min": 1, "max": 9999, "tooltip": "新一轮尝试增加版本号，旧视频保留。更换模型或 LoRA 时必须增加版本号。"}),
            "segment": ("INT", {"default": 1, "min": 1, "max": 3, "tooltip": "先运行第1段，检查满意后改为2，再改为3。"}),
            "stage": (["preview", "final"], {"default": "preview", "tooltip": "preview=4步；final=20步。换档必须从第1段重新跑。"}),
            "megapixels": (["0.4", "0.6", "0.8"], {"default": "0.4", "tooltip": "跟随输入图比例，宽高对齐32。同一条续段链不要中途改。"}),
            "seed": ("INT", {"default": 20261001, "min": 0, "max": 0xffffffffffffffff, "control_after_generate": False, "tooltip": "固定起始种子；每段自动加1。重新尝试建议增加版本号后改种子。"}),
            "attention": (["standard", "sparse_test"], {"default": "standard", "tooltip": "默认稳定路径。sparse_test 为待实测的原生稀疏路径，切换后从第1段重跑。"}),
        }}

    RETURN_TYPES = ("STRING", "INT", "INT", "STRING", "STRING", "STRING", "BOOLEAN", "BOOLEAN", "BOOLEAN", "STRING", "INT", "INT", "INT", "INT", "BOOLEAN", "STRING", "STRING")
    RETURN_NAMES = ("project", "segment", "previous_segment", "video_prefix", "latent_load_path", "latent_save_prefix", "is_continuation", "is_final", "use_reference", "prompt", "frames", "width", "height", "seed", "sparse", "receipt", "status")
    FUNCTION = "build"
    CATEGORY = "Soda/H3"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Recheck files and predecessor receipts on every queue, even after deletion/re-render.
        return float("nan")

    def build(self, plan, image, project, take, segment, stage, megapixels, seed, attention):
        project = project_name(project)
        if segment not in (1, 2, 3) or stage not in ("preview", "final"):
            raise ValueError("请选择有效段号和档位。")
        width, height = canvas(image, megapixels)
        image_hash = hashlib.sha256(image.detach().cpu().contiguous().numpy().tobytes()).hexdigest()
        base = {"schema": 1, "project": project, "take": take, "stage": stage, "width": width, "height": height, "seed": seed, "attention": attention, "image": image_hash, "common": plan["common"]}
        signatures = [digest({**base, "shots": plan["shots"][:i]}) for i in range(1, 4)]
        root = f"h3_context/{stage}/{project}/take_{take:03d}"
        video_root = f"MiniMax_H3/{stage}/{project}/take_{take:03d}"
        # Check the entire prefix: an old clip 2 must not hide a changed clip 1.
        for i in range(1, segment):
            record = output_path(f"{root}/clip_{i:05d}.soda.json")
            if not record.is_file():
                raise ValueError(f"第 {i} 段尚未完整保存。请先用同一项目、版本、档位运行第 {i} 段。")
            previous = json.loads(record.read_text(encoding="utf-8"))
            if previous.get("signature") != signatures[i - 1]:
                raise ValueError(f"第 {i} 段与当前设置不一致。输入图、前段提示词、时长、种子、尺寸或加速模式已变化；请从受影响的前段重新生成，或增加版本号从第1段开始。")
            latent_file = output_path(f"{root}/clip_{i:05d}.safetensors")
            if not latent_file.is_file() or not output_path(previous["video"]).is_file():
                raise ValueError(f"第 {i} 段的视频或 latent 已被移动/删除，请重新生成。")
            stat = latent_file.stat()
            if previous.get("latent_stat") != [stat.st_size, stat.st_mtime_ns]:
                raise ValueError(f"第 {i} 段 latent 已被覆盖但未完整保存视频，请先重新运行第 {i} 段。")
        shot = plan["shots"][segment - 1]
        if not shot["prompt"]:
            raise ValueError(f"请先填写第 {segment} 段提示词。")
        prompt = "\n\n".join(part for part in (plan["common"], shot["prompt"]) if part)
        frames = frame_count(shot["seconds"])
        receipt = {**base, "segment": segment, "signature": signatures[segment-1], "signatures": signatures, "root": root, "video_root": video_root, "prompt": prompt, "frames": frames, "segment_seed": (seed + segment - 1) % (2**64)}
        status = f"{project} / v{take} / {stage} / 第{segment}段 · {width}×{height} · {frames}帧（续段另扣重叠）"
        print(f"[Soda H3] {status}")
        return (project, segment, segment-1, f"{video_root}/{segment:04d}", f"{root}/", f"{root}/clip", segment > 1, stage == "final", False, prompt, frames, width, height, receipt["segment_seed"], attention == "sparse_test", json.dumps(receipt, ensure_ascii=False), status)


def merge_clips(records, target):
    import imageio_ffmpeg
    target.parent.mkdir(parents=True, exist_ok=True)
    listing = target.with_suffix(".concat.txt")
    def quote(path):
        return str(path).replace("\\", "/").replace("'", "'\\''")
    listing.write_text("\n".join(f"file '{quote(output_path(r['video']))}'" for r in records), encoding="utf-8")
    temporary = target.with_name(target.stem + ".tmp.mp4")
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-map", "0:v:0", "-map", "0:a:0?", "-c", "copy", "-movflags", "+faststart", str(temporary)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError("单段已保存，但三段合并失败：" + result.stderr[-1200:])
    os.replace(temporary, target)


class SodaH3Save:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"video": ("VIDEO",), "latent_path": ("STRING", {"forceInput": True}), "receipt": ("STRING", {"forceInput": True})}, "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"}}

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("保存位置",)
    FUNCTION = "save"
    CATEGORY = "Soda/H3"
    OUTPUT_NODE = True

    def save(self, video, latent_path, receipt, prompt=None, extra_pnginfo=None):
        from comfy_api.latest import Types
        data = json.loads(receipt)
        segment = data["segment"]
        expected = output_path(f"{data['root']}/clip_{segment:05d}.safetensors")
        if Path(latent_path).resolve() != expected or not expected.is_file():
            raise ValueError("latent 保存路径与本段不一致，已停止保存完成记录。")
        prefix = f"{data['video_root']}/{segment:04d}"
        w, h = video.get_dimensions()
        directory, filename, counter, subfolder, _ = folder_paths.get_save_image_path(prefix, folder_paths.get_output_directory(), w, h)
        name = f"{filename}_{counter:05d}_.mp4"
        path = Path(directory) / name
        metadata = dict(extra_pnginfo or {})
        if prompt is not None:
            metadata["prompt"] = prompt
        video.save_to(str(path), format=Types.VideoContainer("mp4"), codec=Types.VideoCodec("h264"), metadata=metadata)
        stat = expected.stat()
        data.update(video=path.relative_to(Path(folder_paths.get_output_directory())).as_posix(), latent_stat=[stat.st_size, stat.st_mtime_ns], saved_at=time.time())
        record = output_path(f"{data['root']}/clip_{segment:05d}.soda.json")
        temporary = record.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, record)
        previews = [{"filename": name, "subfolder": subfolder, "type": "output"}]
        message = f"第{segment}段已保存：{path}"
        if segment == 3:
            records = [json.loads(output_path(f"{data['root']}/clip_{i:05d}.soda.json").read_text(encoding="utf-8")) for i in range(1, 4)]
            if any(r["signature"] != data["signatures"][i] for i, r in enumerate(records)):
                raise ValueError("三段设置不一致，未合并。请按当前计划重新生成受影响的段。")
            full = output_path(f"{data['video_root']}/完整三段_{counter:05d}.mp4")
            merge_clips(records, full)
            previews.append({"filename": full.name, "subfolder": data["video_root"], "type": "output"})
            message += f"\n完整三段：{full}"
        print(f"[Soda H3] {message}")
        return {"ui": {"images": previews, "animated": (True,), "text": [message]}, "result": (message,)}


NODE_CLASS_MAPPINGS = {"SodaH3ShotPlan": SodaH3ShotPlan, "SodaH3Studio": SodaH3Studio, "SodaH3Save": SodaH3Save}
NODE_DISPLAY_NAME_MAPPINGS = {"SodaH3ShotPlan": "Soda H3 · 三段分镜", "SodaH3Studio": "Soda H3 · 日常控制", "SodaH3Save": "Soda H3 · 保存与三段合并"}
