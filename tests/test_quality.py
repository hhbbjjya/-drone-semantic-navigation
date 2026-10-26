import json
import unittest
from pathlib import Path
from types import SimpleNamespace

import torch
from transformers import BatchFeature
from roomscan.core import Models
from roomscan.quality import (Generation, attach_evidence, eligible_evidence, render_observation,
                              render_summary, validate_observations, validate_selection)


def output(payload, reason='eos'):
    return Generation(json.dumps(payload, ensure_ascii=False), .1, 40, 256, reason, reason=='eos')


def valid():
    return {'observations': [{'object': '白色櫃子', 'location': '右側', 'uncertain': True}]}


class QualityTests(unittest.TestCase):
    def test_zero_yolo_can_have_separate_vlm_observation(self):
        check = validate_observations(output(valid()))
        observation = {'view_id':'0016','yolo_status':'completed','vlm_status':'completed','detections':[],
                       'vlm_quality':check,'vlm_observations':attach_evidence(check,'0016')}
        text = render_observation(observation)
        self.assertIn('沒有偵測到指定類別',text)
        self.assertIn('白色櫃子',text)
        self.assertFalse(observation['vlm_observations'][0]['human_verified'])
        self.assertEqual(observation['detections'],[])

    def test_valid_json_at_token_limit_is_excluded(self):
        check = validate_observations(output(valid(), 'length'))
        self.assertEqual(check['status'],'rejected')
        self.assertIn('token_limit',check['issues'])
        self.assertEqual(check['observations'],[])

    def test_pretty_json_with_repeated_keys_is_not_a_language_loop(self):
        items=[{'object':name,'location':'中央','uncertain':False} for name in ['桌子','螢幕','鍵盤']]
        generation=Generation(json.dumps({'observations':items},ensure_ascii=False,indent=2),.1,100,256,'eos',True)
        self.assertEqual(validate_observations(generation)['status'],'format_checked')

    def test_nonfinite_duplicate_keys_and_extra_fields_are_rejected(self):
        payloads = ['null', 'true', '[1]', '{"observations":[],"observations":[]}', '{"observations":NaN}',
                    '{"observations":[],"confidence":0.99}', 'Here is JSON: {"observations":[]}']
        for text in payloads:
            with self.subTest(text=text):
                self.assertEqual(validate_observations(Generation(text,.1,20,256,'eos',True))['status'],'rejected')

    def test_single_fence_and_equivalent_array_normalized_without_repair(self):
        text='```json\n'+json.dumps(valid()['observations'],ensure_ascii=False)+'\n```'
        check=validate_observations(Generation(text,.1,40,256,'eos',True))
        self.assertEqual(check['status'],'format_checked')
        self.assertEqual(check['normalizations'],['removed_single_json_fence','wrapped_observation_array'])
        self.assertEqual(validate_observations(Generation(text+' extra claim',.1,40,256,'eos',True))['status'],'rejected')

    def test_missing_uncertainty_is_explicitly_unknown_not_confident(self):
        check=validate_observations(output({'observations':[{'object':'櫃子','location':'中央'}]}))
        self.assertEqual(check['status'],'format_checked')
        item=check['observations'][0]
        self.assertIs(item['uncertain'],True)
        self.assertEqual(item['uncertainty_source'],'missing_default_true')
        self.assertFalse(item['human_verified'])

    def test_duplicate_objects_and_illegal_location_rejected(self):
        item=valid()['observations'][0]
        self.assertIn('duplicate_object',validate_observations(output({'observations':[item,item]}))['issues'])
        item=dict(item,location='距離三公尺')
        self.assertEqual(validate_observations(output({'observations':[item]}))['status'],'rejected')

    def test_summary_cannot_add_unknown_ids_or_rewrite_facts(self):
        check=validate_observations(output(valid()))
        obs={'view_id':'0016','yolo_status':'completed','vlm_status':'completed','detections':[],
             'vlm_quality':check,'vlm_observations':attach_evidence(check,'0016')}
        evidence=eligible_evidence([obs])
        for payload in [{'selected_evidence_ids':['0000:vlm:99']},
                        {'selected_evidence_ids':['0016:vlm:1'],'summary':'已發現十個櫃子'}]:
            self.assertEqual(validate_selection(output(payload),evidence)['status'],'rejected')
        selection=validate_selection(output({'selected_evidence_ids':['0016:vlm:1']}),evidence)
        text=render_summary([obs],selection)
        self.assertIn('[0016]',text)
        self.assertIn('沒有可彙整的 YOLO 偵測',text)
        obs['vlm_quality']={'status':'rejected'}
        self.assertEqual(eligible_evidence([obs]),[])
        self.assertNotIn('白色櫃子',render_summary([obs],selection))

    def test_uploaded_problem_outputs_cannot_enter_v2_summary(self):
        samples=json.loads((Path(__file__).parent/'fixtures/v1_problem_outputs.json').read_text())
        for item in samples:
            check=validate_observations(Generation(item['vlm_answer'],0))
            self.assertEqual(check['status'],'rejected',item['view_id'])
            self.assertEqual(check['observations'],[])
            if item['view_id'] in ['0011','0017']:
                self.assertIn('repetition',check['issues'])
            if item['view_id']=='0016':
                self.assertEqual(item['detections'],[])
                self.assertIn('model_claims_yolo_provenance',check['issues'])

    def test_generate_measures_ids_and_prefers_eos_over_length(self):
        class Processor:
            def apply_chat_template(self,messages,**kwargs):
                assert all(isinstance(message['content'],list) for message in messages)
                return BatchFeature({'input_ids':torch.tensor([[10,11]])})
            tokenizer=SimpleNamespace(decode=lambda *args,**kwargs:'{"observations":[]}')
        class Model:
            generation_config=SimpleNamespace(eos_token_id=[2,3])
            def __init__(self,ids):self.ids=ids
            def generate(self,**kwargs):
                assert kwargs['generation_config'].do_sample is False
                return SimpleNamespace(sequences=torch.tensor([[10,11]+self.ids]))
        backend=Models.__new__(Models)
        backend.device='cpu';backend.torch=torch;backend.processor=Processor()
        for ids,reason in [([50,2],'eos'),([50,51],'length')]:
            backend.vlm=Model(ids)
            result=backend.generate([], 'test',2)
            self.assertEqual(result.generated_tokens,2)
            self.assertEqual(result.finish_reason,reason)
            self.assertEqual(result.eos_observed,reason=='eos')

    def test_describe_does_not_send_detector_list(self):
        backend=Models.__new__(Models);backend.frame_tokens=256
        calls=[]
        def generate(images,prompt,max_tokens):
            calls.append(prompt)
            return output(valid())
        backend.generate=generate
        backend.describe(None,'描述物件','0016')
        self.assertNotIn('confidence',calls[0])
        self.assertNotIn('bbox',calls[0])
        self.assertNotIn('YOLOE 清單',calls[0])


if __name__=='__main__':unittest.main()
