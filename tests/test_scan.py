"""Control-flow tests use a fake model; these do not validate model quality."""
import json
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import trimesh
from PIL import Image

from roomscan.core import Models, Room, Scan
from roomscan.ui import review
from roomscan.quality import Generation


class FakeModels:
    yolo_path = 'test-double'
    vlm_path = 'test-double'
    device = 'test-double'

    def prepare(self, mode):
        pass

    def detect(self, image, directory):
        return image, [{'class': 'laptop', 'confidence': .8, 'bbox_xyxy': [1., 1., 4., 4.],
                        'mask_path': None, 'world_xyz': None, 'validated_3d': False}], .01

    def describe(self, image, question, view_id, retry_issues=()):
        return Generation(json.dumps({'observations': [{'object': '筆電', 'location': '中央', 'uncertain': True}]}, ensure_ascii=False), .02, 40, 256, 'eos', True)

    def summarize(self, room, observations, question, retry_issues=()):
        ids = [o['vlm_observations'][0]['evidence_id'] for o in observations if o.get('vlm_observations')]
        return Generation(json.dumps({'selected_evidence_ids': ids}), .03, 30, 512, 'eos', True)


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        rgb = self.root / 'room' / 'rgb_cam'
        rgb.mkdir(parents=True)
        trimesh.creation.box().export(rgb.parent / 'mesh.obj')
        for i in range(3):
            Image.new('RGB', (12, 8), (i*40, 20, 80)).save(rgb / f'{i:04d}.jpg')
            (rgb / f'{i:04d}.cam').write_text('0 0 0 1 0 0 0 1 0 0 0 1\n.8 0 0 1 .5 .5')
        self.room = Room.load(rgb.parent)

    def job(self, models=None, mode='both'):
        return Scan(self.room, self.root / 'outputs', models or FakeModels(), mode)

    def test_full_run_reports_observations_not_unique_objects(self):
        job = self.job()
        events = list(job.events())
        report = json.loads((job.directory / 'report.json').read_text())
        self.assertGreater(len(events), 3)
        self.assertEqual(report['status'], 'completed')
        self.assertEqual(report['completed_views'], 3)
        self.assertEqual(report['summary_status'], 'completed')
        self.assertEqual(report['objects_by_class'][0]['detection_observations'], 3)
        self.assertIsNone(report['objects_by_class'][0]['unique_object_count'])
        for obs in report['observations']:
            self.assertFalse(obs['camera']['validated'])
            self.assertFalse(obs['detections'][0]['validated_3d'])
        with ZipFile(job.directory / 'results.zip') as z:
            self.assertIsNone(z.testzip())
            self.assertIn('0002/observation.json', z.namelist())
            self.assertEqual(json.loads(z.read('report.json'))['status'], 'completed')
        original, overlay, text = review(str(job.directory / 'report.json'), 2)
        self.assertEqual(original.size, (12, 8))
        self.assertEqual(overlay.size, (12, 8))
        self.assertIn('0001', text)

    def test_stop_after_yolo_preserves_partial_result(self):
        job = self.job()
        for event in job.events():
            if event['phase'] == 'YOLO 偵測完成':
                job.stop.set()
        self.assertEqual(job.report['status'], 'cancelled')
        self.assertEqual(job.report['completed_views'], 0)
        obs = job.report['observations'][0]
        self.assertEqual(obs['yolo_status'], 'completed')
        self.assertEqual(obs['vlm_status'], 'not_run')
        self.assertEqual(obs['status'], 'cancelled')
        self.assertTrue((job.directory / 'results.zip').is_file())

    def test_model_load_error_is_failure_with_report(self):
        class Bad(FakeModels):
            def prepare(self, mode):
                raise RuntimeError('model download blocked')
        job = self.job(Bad())
        list(job.events())
        self.assertEqual(job.report['status'], 'error')
        self.assertEqual(job.report['completed_views'], 0)
        self.assertIn('download blocked', job.report['error'])
        self.assertTrue((job.directory / 'results.zip').is_file())

    def test_detection_failure_not_converted_to_no_detections(self):
        class Bad(FakeModels):
            def detect(self, image, directory):
                raise RuntimeError('test failure')
        job = self.job(Bad())
        list(job.events())
        self.assertEqual(job.report['status'], 'partial')
        self.assertEqual(job.report['failed_views'], 3)
        self.assertEqual(job.report['observations'][0]['vlm_status'], 'skipped_yolo_error')
        self.assertIsNone(job.report['observations'][0]['detections'])

    def test_preview_does_not_claim_inference(self):
        job = self.job(mode='preview')
        list(job.events())
        self.assertEqual(job.report['completed_views'], 3)
        self.assertEqual(job.report['summary_status'], 'not_run')
        self.assertTrue(all(o['yolo_status'] == o['vlm_status'] == 'not_run' for o in job.report['observations']))

    def test_invalid_camera_keeps_image_but_no_position(self):
        (self.room.views[0].image.with_suffix('.cam')).write_text('bad camera')
        room = Room.load(self.room.path)
        self.assertEqual(room.views[0].camera['status'], 'error')
        self.assertIsNone(room.views[0].camera['center_candidate'])

    def test_replay_rejects_path_escape(self):
        job = self.job(mode='preview')
        list(job.events())
        report = job.report
        report['observations'][0]['input_path'] = '../../outside.jpg'
        (job.directory / 'report.json').write_text(json.dumps(report))
        with self.assertRaises(ValueError):
            review(str(job.directory / 'report.json'), 1)

    def test_cancel_during_summary_stays_cancelled(self):
        job = self.job()
        original = job.models.summarize
        def summarize(*args, **kwargs):
            job.stop.set()
            return original(*args, **kwargs)
        job.models.summarize = summarize
        list(job.events())
        self.assertEqual(job.report['status'], 'cancelled')

    def test_summary_error_does_not_erase_successful_views(self):
        class Bad(FakeModels):
            def summarize(self, *args, **kwargs):
                raise RuntimeError('summary failure')
        job = self.job(Bad())
        list(job.events())
        self.assertEqual(job.report['status'], 'partial')
        self.assertEqual(job.report['summary_status'], 'error')
        self.assertEqual(job.report['completed_views'], 3)

    def test_yolo_bgr_overlay_is_converted_to_rgb(self):
        class Result:
            boxes = []
            masks = None
            def plot(self):
                return np.array([[[0, 0, 255]]], dtype=np.uint8)
        class Detector:
            def predict(self, **kwargs):
                return [Result()]
        model = Models.__new__(Models)
        model.device = 'cpu'
        model.confidence = .25
        model.yolo = Detector()
        overlay, detections, _ = model.detect(Image.new('RGB', (1, 1)), self.root)
        self.assertEqual(overlay.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(detections, [])

    def test_rejected_answers_saved_but_never_summarized(self):
        class Bad(FakeModels):
            def describe(self, *args, **kwargs):
                return Generation('YOLOE 清單：白色櫃子', .1, 20, 256, 'eos', True)
            def summarize(self, *args, **kwargs):
                raise AssertionError('Rejected observations must not enter summary')
        job = self.job(Bad())
        list(job.events())
        self.assertEqual(job.report['status'], 'partial')
        self.assertEqual(job.report['quality_rejected_views'], 3)
        self.assertEqual(job.report['summary_status'], 'insufficient_evidence')
        self.assertNotIn('白色櫃子', job.report['summary'])
        for obs in job.report['observations']:
            self.assertEqual(len(obs['vlm_attempts']), 2)
            self.assertEqual(obs['vlm_observations'], [])
            self.assertNotIn('白色櫃子', obs['vlm_answer'])
            self.assertIn('白色櫃子', obs['vlm_attempts'][0]['text'])
        self.assertTrue((job.directory / 'quality_report.json').is_file())

    def test_retry_can_recover_without_altering_detector_facts(self):
        class Retry(FakeModels):
            def describe(self, image, question, view_id, retry_issues=()):
                if not retry_issues:
                    return Generation('not JSON', .1, 20, 256, 'eos', True)
                return super().describe(image, question, view_id, retry_issues)
        job = self.job(Retry())
        list(job.events())
        self.assertEqual(job.report['status'], 'completed')
        for obs in job.report['observations']:
            self.assertEqual(len(obs['vlm_attempts']), 2)
            self.assertEqual(obs['detections'][0]['class'], 'laptop')
            self.assertEqual(obs['vlm_observations'][0]['source'], 'vlm_visual_observation')


if __name__ == '__main__':
    unittest.main()
