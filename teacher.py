"""Routing helpers for H3 reference and two-pass video workflows."""
import json
import math
import uuid

from .studio import output_path, project_name, SodaH3Save


class SodaH3TeacherControl:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "project": ("STRING", {"default": "三段练习", "tooltip": "同一条片保持名称相同。重新开始一条片时换名称。"}),
            "segment": ("INT", {"default": 1, "min": 1, "max": 9999, "tooltip": "1→2→3；首段不用旁路任何节点。"}),
            "upscale": ("BOOLEAN", {"default": False, "label_on": "潜空间放大 + 二采", "label_off": "普通八步", "tooltip": "同一条片不要中途切换；两条路径分别保存。"}),
            "width": ("INT", {"forceInput": True}),
            "height": ("INT", {"forceInput": True}),
            "upscale_mp": ("FLOAT", {"forceInput": True}),
        }}

    RETURN_TYPES = ("INT", "INT", "STRING", "STRING", "BOOLEAN", "STRING")
    RETURN_NAMES = ("本段", "上一段", "读取目录", "保存前缀", "启用放大", "保存信息")
    FUNCTION = "build"
    CATEGORY = "Soda/H3"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def build(self, project, segment, upscale, width, height, upscale_mp):
        project = project_name(project)
        kind = "upscale" if upscale else "standard"
        root = f"h3_context/teacher/{project}/{kind}"
        video_root = f"MiniMax_H3/teacher/{project}/{kind}"
        if upscale:
            factor = math.sqrt(upscale_mp * 1024 * 1024 / (width * height))
            if factor < 1:
                raise ValueError("放大后的像素预算必须大于初始分辨率。")
            dimensions = [round(width * factor / 32) * 32, round(height * factor / 32) * 32]
        else:
            dimensions = [width, height]
        signatures = []
        for i in range(1, segment):
            record = output_path(f"{root}/clip_{i:05d}.soda.json")
            if not record.is_file():
                raise ValueError(f"先用同一项目、同一放大开关生成第 {i} 段，再继续。")
            prior = json.loads(record.read_text(encoding="utf-8"))
            if prior.get("dimensions") != dimensions:
                raise ValueError("前段尺寸不同。请恢复原尺寸，或换项目名从第1段开始。")
            if prior.get("signatures", [])[:i-1] != signatures:
                raise ValueError(f"前段已重做，第 {i} 段仍接着旧结果；请从第 {i} 段重跑。")
            latent = output_path(f"{root}/clip_{i:05d}.safetensors")
            if not latent.is_file() or not output_path(prior["video"]).is_file():
                raise ValueError(f"第 {i} 段文件缺失，请重新生成。")
            stat = latent.stat()
            if prior.get("latent_stat") != [stat.st_size, stat.st_mtime_ns]:
                raise ValueError(f"第 {i} 段保存中断，请重新运行该段。")
            signatures.append(prior["signature"])
        signatures.append(uuid.uuid4().hex)
        data = dict(project=project, segment=segment, root=root, video_root=video_root,
                    dimensions=dimensions, signatures=signatures, signature=signatures[-1])
        return segment, segment - 1, root + "/", root + "/clip", upscale, json.dumps(data, ensure_ascii=False)


class SodaH3TeacherSave(SodaH3Save):
    """Use the existing AV saver; keep a distinct UI name and record namespace."""
    DESCRIPTION = "保存本段视频与续段完成记录。第3段完成后自动合并前三段音视频。"

    def save(self, video, latent_path, receipt, prompt=None, extra_pnginfo=None):
        if list(video.get_dimensions()) != json.loads(receipt)["dimensions"]:
            raise ValueError("输出尺寸与控制区预期不一致，请检查放大尺寸连线。")
        return super().save(video, latent_path, receipt, prompt, extra_pnginfo)


class SodaH3PreviousDecode:
    """Decode pixel context, with a safe no-op for segment one."""
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"latent": ("LATENT",), "vae": ("VAE",), "audio_vae": ("VAE",)}}

    RETURN_TYPES = ("IMAGE", "AUDIO")
    RETURN_NAMES = ("上一段画面", "上一段声音")
    FUNCTION = "decode"
    CATEGORY = "Soda/H3"

    def decode(self, latent, vae, audio_vae):
        if latent is None:
            return None, None
        from nodes import VAEDecode
        from comfy_extras.nodes_audio import VAEDecodeAudio
        samples = latent["samples"]
        if isinstance(samples, (list, tuple)):
            streams = samples
        elif getattr(samples, "is_nested", False):
            streams = samples.unbind()
        else:
            raise ValueError("续段需要同时包含画面和声音的 H3 潜变量。")
        if len(streams) != 2:
            raise ValueError("H3 续段潜变量必须包含画面、声音两个流。")
        # Motion Context's disk loader returns a list; native decoders require
        # one tensor per VAE. Preserve batch dimensions by unpacking the pair.
        video_latent = {**latent, "samples": streams[0]}
        audio_latent = {**latent, "samples": streams[1]}
        images = VAEDecode().decode(vae, video_latent)[0]
        audio = VAEDecodeAudio.execute(vae=audio_vae, samples=audio_latent)[0]
        return images, audio


NODE_CLASS_MAPPINGS = {
    "SodaH3TeacherControl": SodaH3TeacherControl,
    "SodaH3TeacherSave": SodaH3TeacherSave,
    "SodaH3PreviousDecode": SodaH3PreviousDecode,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "SodaH3TeacherControl": "Soda H3 · 项目与段号",
    "SodaH3TeacherSave": "Soda H3 · 保存本段与合片",
    "SodaH3PreviousDecode": "Soda H3 · 放大续段适配",
}
