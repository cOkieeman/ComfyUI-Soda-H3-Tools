import re


_INVALID_PROJECT_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def validate_project_id(project_id):
    value = project_id.strip()
    if not value:
        return "项目名称不能为空。"
    if value in {".", ".."}:
        return "项目名称不能是 . 或 ..。"
    if _INVALID_PROJECT_CHARS.search(value):
        return '项目名称不能包含 < > : " / \\ | ? *。'
    if value.endswith((" ", ".")):
        return "项目名称不能以空格或句点结尾。"
    if len(value) > 80:
        return "项目名称最多 80 个字符。"
    return None


class SodaH3ProjectControl:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "project_id": (
                    "STRING",
                    {
                        "default": "H3_Project",
                        "multiline": False,
                        "tooltip": "同一条分段生成链使用相同的项目名称。",
                    },
                ),
                "segment": (
                    "INT",
                    {
                        "default": 1,
                        "min": 1,
                        "max": 9999,
                        "step": 1,
                        "tooltip": "当前生成段。第 1 段不读取上一段，第 N 段读取 N-1。",
                    },
                ),
                "stage": (
                    ["preview", "final"],
                    {
                        "default": "preview",
                        "tooltip": "预览链和最终链使用不同目录，避免 latent 混用。",
                    },
                ),
                "continuation_style": (
                    ["motion_only", "motion_plus_reference"],
                    {
                        "default": "motion_only",
                        "tooltip": (
                            "续段默认只使用上一段 Motion Context latent，减少参考图重新解释服装/身体状态。"
                            "需要长期强化人物身份时选择 motion_plus_reference。"
                        ),
                    },
                ),
            }
        }

    RETURN_TYPES = (
        "STRING", "INT", "INT", "STRING", "STRING", "STRING",
        "BOOLEAN", "BOOLEAN", "BOOLEAN",
    )
    RETURN_NAMES = (
        "project_id",
        "segment",
        "previous_segment",
        "video_prefix",
        "latent_load_path",
        "latent_save_prefix",
        "is_continuation",
        "is_final",
        "use_reference_on_continuation",
    )
    FUNCTION = "build"
    CATEGORY = "Soda/H3"
    DESCRIPTION = "集中生成 H3 项目名、段号、视频输出和 Motion Context latent 路径。"

    @classmethod
    def VALIDATE_INPUTS(cls, project_id, segment, stage, continuation_style="motion_only"):
        error = validate_project_id(project_id)
        if error:
            return error
        if segment < 1:
            return "当前段必须大于或等于 1。"
        if stage not in {"preview", "final"}:
            return "阶段只能是 preview 或 final。"
        if continuation_style not in {"motion_only", "motion_plus_reference"}:
            return "续段策略只能是 motion_only 或 motion_plus_reference。"
        return True

    def build(self, project_id, segment, stage, continuation_style="motion_only"):
        project_id = project_id.strip()
        previous_segment = segment - 1
        root = f"h3_context/{stage}/{project_id}"
        return (
            project_id,
            segment,
            previous_segment,
            f"MiniMax_H3/{stage}/{project_id}/{segment:04d}",
            f"{root}/",
            f"{root}/clip",
            segment > 1,
            stage == "final",
            continuation_style == "motion_plus_reference",
        )


NODE_CLASS_MAPPINGS = {
    "SodaH3ProjectControl": SodaH3ProjectControl,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "SodaH3ProjectControl": "Soda H3 项目控制",
}
