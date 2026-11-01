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
def reject_constant(token):raise ValueError(token)
def strict_json(raw,label):
    # Decode like the host (TextDecoder('utf-8',{fatal:true}) and JSON.parse): no UTF-16/UTF-32, no byte order mark, no NaN or Infinity.
    try:return json.loads(raw.decode('utf-8'),parse_constant=reject_constant)
    except ValueError:raise SystemExit(f'cleantv-catalog.json: {label} must be UTF-8 JSON without a byte order mark, NaN or Infinity')
def units(value):return len(value.encode('utf-16-le','surrogatepass'))//2
def host_limits(item,label):
    # The host measures String.length (UTF-16 code units); JSON Schema maxLength counts code points, so an emoji counts twice on the TV.
    # One entry over a host limit fails the whole catalog refresh on every TV.
    for key,limit in (('name',240),('description',240),('author',240),('license',240),('text',500),('timeZone',64)):
        if isinstance(item.get(key),str):require(units(item[key])<=limit,f'{label}: {key} exceeds {limit} UTF-16 code units (Samsung host limit)')
def canonical(value):return json.dumps(value,sort_keys=True,ensure_ascii=False)
cleantv_schema=json.loads((root/'cleantv-catalog.schema.json').read_bytes())
# Kinds that package.schema.json does not know keep their packages in cleantv-packages/, outside the upstream packages/ loop above.
cleantv_only={}
for kind in ('weather','wallpapers'):
    source=cleantv_schema['definitions'][kind]
    cleantv_only[kind]=Draft7Validator(dict(source,
        required=[key for key in source['required'] if key not in ('path','sha256')],
        properties={key:value for key,value in source['properties'].items() if key not in ('path','sha256')},
        definitions=cleantv_schema['definitions']))
cleantv_raw=(root/'cleantv-catalog.json').read_bytes()
# The Samsung host refuses catalog responses above 128 KiB.
require(len(cleantv_raw)<=131072,'catalog exceeds 131072 bytes')
cleantv=strict_json(cleantv_raw,'the catalog')
Draft7Validator(cleantv_schema).validate(cleantv)
require(cleantv['api']==2 and len(cleantv['addons'])<=32,'api must be 2 with at most 32 entries')
cleantv_ids=set()
for entry in cleantv['addons']:
    name=entry['id']
    require(name not in cleantv_ids,f'duplicate id {name}')
    cleantv_ids.add(name)
    host_limits(entry,name)
    folder='cleantv-packages' if entry['kind'] in cleantv_only else 'packages'
    require(entry['path']==f"{folder}/{name}/{entry['version']}.json",f'{name}: path must be {folder}/<id>/<version>.json')
    file=root/entry['path']
    require(file.is_file(),f"{name}: {entry['path']} does not exist")
    data=file.read_bytes()
    require(len(data)<=65536,f'{name}: package exceeds 65536 bytes')
    require(hashlib.sha256(data).hexdigest()==entry['sha256'],f"{name}: sha256 does not match the bytes of {entry['path']}")
    package={key:value for key,value in entry.items() if key not in ('path','sha256')}
    # Compared as canonical JSON: Python == treats true, 1 and 1.0 as equal.
    require(canonical(strict_json(data,entry['path']))==canonical(package),f'{name}: package must equal the entry without path and sha256')
    if 'timeZone' in entry:ZoneInfo(entry['timeZone'])
# The upstream loop never sees cleantv-packages/, so every file there gets its kind's package checks here.
cleantv_dir=root/'cleantv-packages'
for file in sorted(cleantv_dir.rglob('*.json')) if cleantv_dir.is_dir() else []:
    label=file.relative_to(root).as_posix()
    data=file.read_bytes()
    require(len(data)<=65536,f'{label}: package exceeds 65536 bytes')
    item=strict_json(data,label)
    require(isinstance(item,dict) and isinstance(item.get('kind'),str) and item['kind'] in cleantv_only,f"{label}: only {', '.join(cleantv_only)} packages belong in cleantv-packages/")
    cleantv_only[item['kind']].validate(item)
    require(label==f"cleantv-packages/{item['id']}/{item['version']}.json",f'{label}: path must be cleantv-packages/<id>/<version>.json')
    host_limits(item,label)
print('CleanTV catalog, checksums and packages validated.')

# CleanTV wallpapers: index.json and generated/ come from cleantv-wallpapers/tools/generate.py.
# The Samsung host refuses an index above 262144 bytes or 200 entries and downloads each file by its exact size and sha256.
WALLPAPER_FILES={'jpg':'image.jpg','thumb':'thumb.jpg','panel':'panel.jpg','study-soft':'study-soft.jpg','field-blur':'field-blur.jpg','field-frost':'field-frost.jpg','field-clear':'field-clear.jpg'}
WALLPAPER_LIMITS={'jpg':4194304,'thumb':262144,'panel':65536,'study-soft':2097152,'field-blur':2097152,'field-frost':2097152,'field-clear':2097152}
def wallpaper_require(condition,message):
    if not condition:raise SystemExit('cleantv-wallpapers/index.json: '+message)
wallpaper_root=root/'cleantv-wallpapers'
wallpaper_index=wallpaper_root/'index.json'
if any(entry['kind']=='wallpapers' for entry in cleantv['addons']) or wallpaper_index.exists():
    wallpaper_require(wallpaper_index.is_file(),'missing; a wallpapers package needs the generated index')
    raw=wallpaper_index.read_bytes()
    wallpaper_require(len(raw)<=262144,f'{len(raw)} bytes exceeds 262144 (Samsung host limit)')
    try:index=json.loads(raw.decode('utf-8'),parse_constant=reject_constant)
    except ValueError:raise SystemExit('cleantv-wallpapers/index.json: must be UTF-8 JSON without a byte order mark, NaN or Infinity')
    Draft7Validator(json.loads((wallpaper_root/'index.schema.json').read_bytes())).validate(index)
    wallpaper_require(len(index['entries'])<=200,'more than 200 entries')
    wallpaper_ids=set();referenced=set()
    for entry in index['entries']:
        wid=entry['id']
        wallpaper_require(wid not in wallpaper_ids,f'duplicate id {wid}')
        wallpaper_ids.add(wid)
        wallpaper_require(units(entry['title'])<=120,f'{wid}: title exceeds 120 UTF-16 code units (Samsung host limit)')
        wallpaper_require(entry['rev']==entry['files']['jpg']['sha256'][:12],f'{wid}: rev must be the first 12 hex digits of the jpg sha256')
        for role,name in WALLPAPER_FILES.items():
            item=entry['files'][role];path=f'cleantv-wallpapers/generated/{wid}/{name}'
            wallpaper_require(item['path']==path,f'{wid}: the {role} path must be {path}')
            wallpaper_require(item['size']<=WALLPAPER_LIMITS[role],f'{wid}: {role} exceeds {WALLPAPER_LIMITS[role]} bytes')
            file=root/path
            wallpaper_require(file.is_file(),f'{wid}: {path} does not exist')
            data=file.read_bytes()
            wallpaper_require(len(data)==item['size'],f"{wid}: {path} has {len(data)} bytes, not {item['size']}")
            wallpaper_require(hashlib.sha256(data).hexdigest()==item['sha256'],f'{wid}: sha256 does not match the bytes of {path}')
            referenced.add(path)
    generated=wallpaper_root/'generated'
    # Removing an image removes its folder, so nothing in generated/ may be left without an entry.
    stray=sorted(p.relative_to(root).as_posix() for p in generated.rglob('*') if p.is_file() and p.relative_to(root).as_posix() not in referenced) if generated.is_dir() else []
    wallpaper_require(not stray,'files in generated/ that no entry references: '+', '.join(stray[:5]))
    print(f"CleanTV wallpaper index validated ({len(index['entries'])} entries).")
