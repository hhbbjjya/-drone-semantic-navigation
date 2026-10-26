import unittest
from roomscan.vocabulary import resolve_classes,RESEARCH_CLASSES
from roomscan.core import CLASSES

class VocabularyTests(unittest.TestCase):
    def test_default_is_full_lvis_including_previously_excluded_targets(self):
        names=resolve_classes()
        self.assertEqual(len(names),1203)
        self.assertEqual(len(set(names)),1203)
        self.assertEqual(CLASSES,names)
        for name in ['fan','cabinet','refrigerator']:
            self.assertIn(name,names)

    def test_coco_full_80_and_legacy_are_available(self):
        names=resolve_classes('coco')
        self.assertEqual(len(names),80)
        for name in ['person','book','bottle','refrigerator']:
            self.assertIn(name,names)
        self.assertEqual(resolve_classes('research'),RESEARCH_CLASSES)

    def test_custom_is_explicit_and_cannot_be_empty(self):
        self.assertEqual(resolve_classes('custom',' fan, cabinet,fan '),['fan','cabinet'])
        for vocab,custom in [('custom',' , '),('unknown',None)]:
            with self.assertRaises(ValueError):resolve_classes(vocab,custom)

    def test_resolving_returns_a_copy(self):
        names=resolve_classes();names.clear()
        self.assertEqual(len(resolve_classes()),1203)

if __name__=='__main__':unittest.main()
