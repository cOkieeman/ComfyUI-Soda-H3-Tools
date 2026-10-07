"""Check ComfyUI's package entry point without importing GPU dependencies."""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


class RegistrationTests(unittest.TestCase):
    def test_legacy_ids_and_current_names_remain_available(self):
        root = Path(__file__).resolve().parents[1]
        package_name = 'soda_registration_test'
        spec = importlib.util.spec_from_file_location(
            package_name, root / '__init__.py',
            submodule_search_locations=[str(root)],
        )
        package = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {
            package_name: package,
            'folder_paths': types.ModuleType('folder_paths'),
        }):
            spec.loader.exec_module(package)
            expected = {
                'SodaH3ProjectControl', 'SodaH3ShotPlan', 'SodaH3Studio',
                'SodaH3Save', 'SodaH3TeacherControl', 'SodaH3TeacherSave',
                'SodaH3PreviousDecode',
            }
            self.assertEqual(set(package.NODE_CLASS_MAPPINGS), expected)
            self.assertEqual(set(package.NODE_DISPLAY_NAME_MAPPINGS), expected)
            for name, node in package.NODE_CLASS_MAPPINGS.items():
                with self.subTest(node=name):
                    self.assertTrue(callable(getattr(node, node.FUNCTION)))
                    self.assertIn('required', node.INPUT_TYPES())
                    self.assertNotIn('teacher', package.NODE_DISPLAY_NAME_MAPPINGS[name].lower())

    def test_output_path_cannot_escape_output_directory(self):
        # Reuse the isolated loader in the sequence regression tests.
        from test_sequence import folder, studio
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            with patch.object(folder, 'get_output_directory', return_value=directory, create=True):
                with self.assertRaisesRegex(ValueError, 'ComfyUI/output'):
                    studio.output_path('../outside.mp4')


if __name__ == '__main__':
    unittest.main()
