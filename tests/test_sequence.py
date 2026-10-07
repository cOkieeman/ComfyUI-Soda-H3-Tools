import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent
PLUGIN = HERE.parent
package = types.ModuleType('soda_sequence_test')
package.__path__ = [str(PLUGIN)]
sys.modules[package.__name__] = package
folder = types.ModuleType('folder_paths')
sys.modules['folder_paths'] = folder
for name in ('studio', 'teacher'):
    spec = importlib.util.spec_from_file_location(f'{package.__name__}.{name}', PLUGIN / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
teacher = module
studio = sys.modules[package.__name__ + '.studio']


class SequenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        folder.get_output_directory = lambda: self.temp.name
        self.args = dict(project='练习', segment=1, upscale=False, width=544, height=704, upscale_mp=0.8)

    def tearDown(self):
        self.temp.cleanup()

    def control(self):
        return teacher.SodaH3TeacherControl().build(**self.args)

    def record(self, segment):
        self.args['segment'] = segment
        data = json.loads(self.control()[-1])
        latent = studio.output_path(f"{data['root']}/clip_{segment:05d}.safetensors")
        latent.parent.mkdir(parents=True, exist_ok=True)
        latent.write_bytes(b'unit-test-latent')
        video = studio.output_path(f"{data['video_root']}/{segment}.mp4")
        video.parent.mkdir(parents=True, exist_ok=True)
        video.write_bytes(b'unit-test-video')
        stat = latent.stat()
        data.update(video=video.relative_to(self.temp.name).as_posix(), latent_stat=[stat.st_size, stat.st_mtime_ns])
        studio.output_path(f"{data['root']}/clip_{segment:05d}.soda.json").write_text(json.dumps(data),encoding='utf-8')
        return data

    def test_first_segment_needs_no_previous_file_or_decode(self):
        self.assertEqual(self.control()[1], 0)
        self.assertEqual(teacher.SodaH3PreviousDecode().decode(None, None, None), (None, None))

    def test_previous_decode_splits_loaded_and_live_av_without_mutation(self):
        video, audio = object(), object()
        class Nested:
            is_nested = True
            def unbind(self): return video, audio
        video_node = types.SimpleNamespace(VAEDecode=lambda: types.SimpleNamespace(
            decode=lambda vae, samples: (samples['samples'],)))
        audio_node = types.SimpleNamespace(VAEDecodeAudio=types.SimpleNamespace(
            execute=lambda vae, samples: (samples['samples'],)))
        with patch.dict(sys.modules, {'nodes': video_node, 'comfy_extras': types.ModuleType('comfy_extras'), 'comfy_extras.nodes_audio': audio_node}):
            for samples in ([video, audio], (video, audio), Nested()):
                latent = {'samples': samples}
                result = teacher.SodaH3PreviousDecode().decode(latent, None, None)
                self.assertEqual(result, (video, audio))
                self.assertIs(latent['samples'], samples)
            with self.assertRaisesRegex(ValueError, '两个流'):
                teacher.SodaH3PreviousDecode().decode({'samples': [video]}, None, None)

    def test_order_and_successful_three_segment_chain(self):
        self.args['segment'] = 2
        with self.assertRaisesRegex(ValueError, '先用同一项目'): self.control()
        one = self.record(1)
        two = self.record(2)
        self.args['segment'] = 3
        three = json.loads(self.control()[-1])
        self.assertEqual(three['signatures'][:2], [one['signature'], two['signature']])

    def test_rerendered_first_requires_rerendering_second(self):
        self.record(1); self.record(2); self.record(1)
        self.args['segment'] = 3
        with self.assertRaisesRegex(ValueError, '仍接着旧结果'): self.control()

    def test_dimensions_and_modes_cannot_mix(self):
        self.record(1); self.args['segment'] = 2
        self.args['width'] = 576
        with self.assertRaisesRegex(ValueError, '尺寸不同'): self.control()
        self.args['width'] = 544; self.args['upscale'] = True
        with self.assertRaisesRegex(ValueError, '先用同一项目'): self.control()

    def test_interrupted_save_is_not_a_valid_predecessor(self):
        data = self.record(1)
        studio.output_path(f"{data['root']}/clip_00001.safetensors").write_bytes(b'overwritten')
        self.args['segment'] = 2
        with self.assertRaisesRegex(ValueError, '保存中断'): self.control()

    def test_upscale_alignment_matches_upstream(self):
        self.args['upscale'] = True
        d = json.loads(self.control()[-1])['dimensions']
        self.assertEqual(d, [800, 1056])

    def test_paths_reject_windows_reserved_names(self):
        for value in ['../x', 'NUL', 'CON.txt', 'x/y', '']:
            self.args['project'] = value
            with self.assertRaises(ValueError): self.control()

if __name__ == '__main__': unittest.main(verbosity=2)
