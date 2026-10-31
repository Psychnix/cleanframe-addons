import hashlib,json
from pathlib import Path
from zoneinfo import ZoneInfo
from jsonschema import Draft7Validator
root=Path(__file__).resolve().parents[1]
validator=Draft7Validator(json.loads((root/'package.schema.json').read_text()))
catalog=json.loads((root/'catalog.json').read_text())
assert catalog['api']==1 and len(catalog['addons'])<=32
ids=set()
for entry in catalog['addons']:
    assert entry['id'] not in ids
    ids.add(entry['id'])
    assert entry['path']==f"packages/{entry['id']}/{entry['version']}.json"
    data=(root/entry['path']).read_bytes()
    assert len(data)<=65536 and hashlib.sha256(data).hexdigest()==entry['sha256']
    package=json.loads(data);validator.validate(package)
    for key in package:assert package[key]==entry[key]
for path in list((root/'packages').rglob('*.json'))+list((root/'examples').glob('*.json')):
    item=json.loads(path.read_text());validator.validate(item)
    if item['kind']=='spotify':assert item['id']=='spotify'
    if 'timeZone' in item:ZoneInfo(item['timeZone'])
print('Catalog, checksums and example packages validated.')

# API 2 keeps all API 1 metadata complete and never mutates the legacy catalog.
v2=json.loads((root/'catalog-v2.json').read_text())
assert v2['api']==2 and len(v2['addons'])<=32
native_schema=json.loads((root/'native-package.schema.json').read_text())
native_validator=Draft7Validator(native_schema)
catalog_schema=json.loads((root/'catalog-v2.schema.json').read_text())
# Resolve the sole local reference without permitting schema network requests.
catalog_schema['properties']['addons']['items']['oneOf'][0]=native_schema
Draft7Validator(catalog_schema).validate(v2)
v2ids=set()
for entry in v2['addons']:
    assert entry['id'] not in v2ids
    v2ids.add(entry['id'])
    if entry['kind']=='native':
        native_validator.validate(entry)
    else:
        package={key:value for key,value in entry.items() if key not in ('path','sha256')}
        validator.validate(package)
        assert entry['path']==f"packages/{entry['id']}/{entry['version']}.json"
        data=(root/entry['path']).read_bytes()
        assert len(data)<=65536 and hashlib.sha256(data).hexdigest()==entry['sha256']
        assert json.loads(data)==package
for legacy in catalog['addons']:
    assert legacy in v2['addons'], 'API 2 must retain the complete existing API 1 entries'
print('API 2 catalog validated; native entries require separate signed-artifact and device acceptance.')

# CleanTV Samsung catalog: a separate file, so catalog.json and catalog-v2.json and their checks stay as upstream.
def require(condition,message):
    if not condition:raise SystemExit('cleantv-catalog.json: '+message)
cleantv_raw=(root/'cleantv-catalog.json').read_bytes()
# The Samsung host refuses catalog responses above 128 KiB.
require(len(cleantv_raw)<=131072,'catalog exceeds 131072 bytes')
cleantv=json.loads(cleantv_raw)
Draft7Validator(json.loads((root/'cleantv-catalog.schema.json').read_bytes())).validate(cleantv)
require(cleantv['api']==2 and len(cleantv['addons'])<=32,'api must be 2 with at most 32 entries')
cleantv_ids=set()
for entry in cleantv['addons']:
    name=entry['id']
    require(name not in cleantv_ids,f'duplicate id {name}')
    cleantv_ids.add(name)
    require(entry['path']==f"packages/{name}/{entry['version']}.json",f'{name}: path must be packages/<id>/<version>.json')
    file=root/entry['path']
    require(file.is_file(),f"{name}: {entry['path']} does not exist")
    data=file.read_bytes()
    require(len(data)<=65536,f'{name}: package exceeds 65536 bytes')
    require(hashlib.sha256(data).hexdigest()==entry['sha256'],f"{name}: sha256 does not match the bytes of {entry['path']}")
    package={key:value for key,value in entry.items() if key not in ('path','sha256')}
    require(json.loads(data)==package,f'{name}: package must equal the entry without path and sha256')
    if 'timeZone' in entry:ZoneInfo(entry['timeZone'])
print('CleanTV catalog, checksums and packages validated.')
