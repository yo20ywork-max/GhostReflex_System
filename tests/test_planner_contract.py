"""Check production prompt/schema compatibility without starting desktop hooks."""
import json,sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'finetuning'))
from build_product_data import contract,check

class PlannerContract(unittest.TestCase):
    def test_output_schema_is_present_and_roundtrips(self):
        catalog,schema,prompt,_=contract()
        system=prompt(SimpleNamespace(catalog=catalog,schema=schema))
        serialized=system.split('輸出 JSON Schema（欄位名稱與型別必須一致）：\n',1)[1]
        displayed=json.loads(serialized)
        self.assertEqual(displayed['properties']['steps']['maxItems'],schema['properties']['steps']['maxItems'])
        self.assertEqual(prompt(SimpleNamespace(catalog=catalog)),system)
        branches=schema['properties']['steps']['items']['oneOf']
        self.assertEqual(len(branches),len(catalog))
        self.assertIn('tool',displayed['properties']['steps']['items']['properties'])
        self.assertNotIn('tool_name',displayed['properties']['steps']['items']['properties'])
        self.assertEqual({b['properties']['tool']['enum'][0] for b in branches},{t['name'] for t in catalog})
    def test_runtime_schema_override_is_not_replaced_by_training_default(self):
        catalog,schema,prompt,_=contract()
        custom=json.loads(json.dumps(schema));custom['properties']['steps']['maxItems']=3
        system=prompt(SimpleNamespace(catalog=catalog,schema=custom))
        displayed=json.loads(system.split('輸出 JSON Schema（欄位名稱與型別必須一致）：\n')[1])
        self.assertEqual(displayed['properties']['steps']['maxItems'],3)

    def test_tools_and_arguments_are_jointly_constrained(self):
        from jsonschema import Draft202012Validator
        catalog,schema,_,_=contract(explicit_tool_defaults=True)
        validator=Draft202012Validator(schema)
        def plan(tool,args):
            return {'objective':'驗證','assumptions':[], 'steps':[{'id':1,'goal':'執行','tool':tool,'args':args,'success_check':'讀回結果'}],'completion_criteria':['符合要求']}
        validator.validate(plan('BROWSER_PRESS',{'key':'Enter','by':'label','target':'標題'}))
        self.assertFalse(validator.is_valid(plan('BROWSER_PRESS',{'key':'Enter','by':'label','target':'標題','exact':True})))
        self.assertFalse(validator.is_valid(plan('BROWSER_PRESS',{'key':'Enter','by':'label','target':'標題','exact':False})))
        self.assertFalse(validator.is_valid(plan('LIST_DIRECTORY',{'path':'.','recursive':'false'})))
        validator.validate(plan('LIST_DIRECTORY',{'path':'.','recursive':False,'max_items':'{{step:9.output}}'}))
        self.assertFalse(validator.is_valid(plan('LIST_DIRECTORY',{'path':'.','recursive':False})))
        self.assertFalse(validator.is_valid(plan('LIST_DIRECTORY',{'path':'.','max_items':'{{step:0.output}}'})))

if __name__=='__main__':unittest.main()
