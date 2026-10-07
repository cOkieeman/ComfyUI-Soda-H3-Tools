import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "nodes.py"
SPEC = importlib.util.spec_from_file_location("soda_h3_nodes", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SodaH3ProjectControlTests(unittest.TestCase):
    def test_first_preview_segment(self):
        result = MODULE.SodaH3ProjectControl().build("demo", 1, "preview", "motion_only")
        self.assertEqual(
            result,
            (
                "demo",
                1,
                0,
                "MiniMax_H3/preview/demo/0001",
                "h3_context/preview/demo/",
                "h3_context/preview/demo/clip",
                False,
                False,
                False,
            ),
        )

    def test_continuation_final_segment(self):
        result = MODULE.SodaH3ProjectControl().build(
            "demo-02", 12, "final", "motion_plus_reference"
        )
        self.assertEqual(result[2], 11)
        self.assertEqual(result[3], "MiniMax_H3/final/demo-02/0012")
        self.assertEqual(result[5], "h3_context/final/demo-02/clip")
        self.assertTrue(result[6])
        self.assertTrue(result[7])
        self.assertTrue(result[8])

    def test_rejects_path_characters(self):
        self.assertIsInstance(
            MODULE.SodaH3ProjectControl.VALIDATE_INPUTS(
                "../demo", 1, "preview", "motion_only"
            ),
            str,
        )

    def test_accepts_chinese_project_name(self):
        self.assertTrue(
            MODULE.SodaH3ProjectControl.VALIDATE_INPUTS(
                "短片_第一版", 1, "preview", "motion_only"
            )
        )

    def test_rejects_unknown_continuation_style(self):
        self.assertIsInstance(
            MODULE.SodaH3ProjectControl.VALIDATE_INPUTS(
                "demo", 2, "preview", "unknown"
            ),
            str,
        )


if __name__ == "__main__":
    unittest.main()
