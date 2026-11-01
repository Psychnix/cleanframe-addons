"""Regression tests for the CleanTV section of scripts/validate.py.

Each case copies the validation inputs into a temporary directory, changes the
CleanTV catalog or its packages and runs the real validate.py there. The cases
cover gaps where validate.py once passed a catalog that the Samsung host rejects
for every TV (UTF-16 lengths, non-UTF-8 encodings) or could never accept a valid
package (weather and wallpapers outside the upstream packages/ directory).
"""
import hashlib,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path

repo=Path(__file__).resolve().parents[1]
INPUTS=['catalog.json','catalog-v2.json','catalog-v2.schema.json','native-package.schema.json','package.schema.json','cleantv-catalog.json','cleantv-catalog.schema.json']
FOLDERS=['packages','examples','cleantv-packages']
HELLO='packages/cleantv-hello/1.0.0.json'

def copy_inputs(target):
    # A Windows checkout with core.autocrlf has CRLF files; the committed bytes, which the hashes cover, are LF.
    def put(source,destination):
        destination.parent.mkdir(parents=True,exist_ok=True)
        data=source.read_bytes()
        destination.write_bytes(data.replace(b'\r\n',b'\n') if source.suffix in ('.json','.py') else data)
    put(repo/'scripts'/'validate.py',target/'scripts'/'validate.py')
    for name in INPUTS:put(repo/name,target/name)
    for folder in FOLDERS:
        if (repo/folder).is_dir():
            for source in (repo/folder).rglob('*'):
                if source.is_file():put(source,target/source.relative_to(repo))

def dump(value):
    try:return (json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
    except UnicodeEncodeError:return (json.dumps(value,indent=2)+'\n').encode('utf-8')  # lone surrogates stay escaped

class Fixture:
    def __init__(self,root):
        self.root=root
        self.catalog=json.loads((root/'cleantv-catalog.json').read_bytes().decode('utf-8'))
    def entry(self,name):return next(entry for entry in self.catalog['addons'] if entry['id']==name)
    def package(self,entry,data=None):
        """Write the package for an entry (its own fields unless data is given) and record its hash."""
        package={key:value for key,value in entry.items() if key not in ('path','sha256')}
        data=dump(package) if data is None else data
        file=self.root/entry['path']
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_bytes(data)
        entry['sha256']=hashlib.sha256(data).hexdigest()
    def add(self,entry,data=None):
        self.catalog['addons'].append(entry)
        self.package(entry,data)
    def save(self,data=None):(self.root/'cleantv-catalog.json').write_bytes(dump(self.catalog) if data is None else data)

def weather(**extra):
    entry={'api':1,'id':'cleantv-weather','name':'Weather','version':'1.0.0','kind':'weather','description':'Weather below the clock','author':'Psychnix','license':'MIT','path':'cleantv-packages/cleantv-weather/1.0.0.json','sha256':''}
    entry.update(extra)
    return entry

def wallpapers(**extra):
    entry={'api':1,'id':'cleantv-wallpapers','name':'Wallpapers','version':'1.0.0','kind':'wallpapers','description':'Wallpaper collection','author':'Psychnix','license':'MIT','index':'cleantv-wallpapers/index.json','path':'cleantv-packages/cleantv-wallpapers/1.0.0.json','sha256':''}
    entry.update(extra)
    return entry

def rehello(fixture,**fields):
    entry=fixture.entry('cleantv-hello')
    entry.update(fields)
    fixture.package(entry)
    fixture.save()

EMOJI='\U0001F3B5'
CASES=[]
def case(name,passes,expect=''):
    def register(change):
        CASES.append((name,change,passes,expect))
        return change
    return register

@case('unchanged catalog',True)
def _(f):pass

@case('name of 120 astral characters is exactly 240 UTF-16 units',True)
def _(f):rehello(f,name=EMOJI*120)

@case('name of 130 astral characters is 260 UTF-16 units',False,'cleantv-hello: name exceeds 240 UTF-16 code units')
def _(f):rehello(f,name=EMOJI*130)

@case('description of 238 letters and 2 astral characters is 242 units',False,'cleantv-hello: description exceeds 240 UTF-16 code units')
def _(f):rehello(f,description='a'*238+EMOJI*2)

@case('author over 240 units',False,'cleantv-hello: author exceeds 240')
def _(f):rehello(f,author=EMOJI*121)

@case('license over 240 units',False,'cleantv-hello: license exceeds 240')
def _(f):rehello(f,license=EMOJI*121)

@case('text of 250 astral characters is exactly 500 units',True)
def _(f):rehello(f,text='\U0001F324'*250)

@case('text of 300 astral characters is 600 units',False,'cleantv-hello: text exceeds 500 UTF-16 code units')
def _(f):rehello(f,text='\U0001F324'*300)

@case('lone surrogate counts as one unit',True)
def _(f):rehello(f,name='\ud800'*240)

@case('weather entry over the host limit',False,'cleantv-weather: name exceeds 240')
def _(f):
    f.add(weather(name=EMOJI*121));f.save()

@case('catalog encoded as UTF-16 with BOM',False,'the catalog must be UTF-8 JSON')
def _(f):f.save(dump(f.catalog).decode('utf-8').encode('utf-16'))

@case('catalog encoded as UTF-16-LE without BOM',False,'the catalog must be UTF-8 JSON')
def _(f):f.save(dump(f.catalog).decode('utf-8').encode('utf-16-le'))

@case('catalog encoded as UTF-32 with BOM',False,'the catalog must be UTF-8 JSON')
def _(f):f.save(dump(f.catalog).decode('utf-8').encode('utf-32'))

@case('catalog with a UTF-8 byte order mark',False,'the catalog must be UTF-8 JSON')
def _(f):f.save(b'\xef\xbb\xbf'+dump(f.catalog))

@case('catalog with NaN',False,'the catalog must be UTF-8 JSON')
def _(f):f.save(dump(f.catalog).replace(b'"api": 2',b'"api": NaN',1))

@case('the id constructor, which the host refuses',False,'ValidationError')
def _(f):
    f.add(weather(id='constructor',path='cleantv-packages/constructor/1.0.0.json'));f.save()

@case('weather package in cleantv-packages',True)
def _(f):
    f.add(weather());f.save()

@case('wallpapers package in cleantv-packages',True)
def _(f):
    f.add(wallpapers());f.save()

@case('weather and wallpapers together',True)
def _(f):
    f.add(weather());f.add(wallpapers());f.save()

@case('weather entry under packages/',False,'ValidationError')
def _(f):
    f.add(weather(path='packages/cleantv-weather/1.0.0.json'));f.save()

@case('text entry under cleantv-packages/',False,'ValidationError')
def _(f):
    entry=f.entry('cleantv-hello');entry['path']='cleantv-packages/cleantv-hello/1.0.0.json'
    f.package(entry);f.save()

@case('weather entry with a wrong version in its path',False,'cleantv-weather: path must be cleantv-packages/<id>/<version>.json')
def _(f):
    f.add(weather(path='cleantv-packages/cleantv-weather/1.0.1.json'));f.save()

@case('weather package that says true where the entry says 1',False,'package must equal the entry')
def _(f):
    entry=weather();package={key:value for key,value in entry.items() if key not in ('path','sha256')};package['api']=True
    f.add(entry,dump(package));f.save()

@case('weather package that says 1.0 where the entry says 1',False,'cleantv-weather: package must equal the entry')
def _(f):
    entry=weather();f.add(entry,dump({key:value for key,value in entry.items() if key not in ('path','sha256')}).replace(b'"api": 1,',b'"api": 1.0,',1));f.save()

@case('weather package encoded as UTF-16',False,'cleantv-packages/cleantv-weather/1.0.0.json must be UTF-8 JSON')
def _(f):
    entry=weather();f.add(entry,dump({key:value for key,value in entry.items() if key not in ('path','sha256')}).decode('utf-8').encode('utf-16'));f.save()

@case('unlisted text package in cleantv-packages/',False,'only weather, wallpapers packages belong in cleantv-packages/')
def _(f):
    file=f.root/'cleantv-packages'/'cleantv-note'/'1.0.0.json';file.parent.mkdir(parents=True)
    file.write_bytes(dump({'api':1,'id':'cleantv-note','name':'Note','version':'1.0.0','kind':'text','description':'Note','author':'Psychnix','license':'MIT'}))

@case('unlisted weather package with an extra field',False,'ValidationError')
def _(f):
    file=f.root/'cleantv-packages'/'cleantv-weather'/'0.9.0.json';file.parent.mkdir(parents=True)
    file.write_bytes(dump({'api':1,'id':'cleantv-weather','name':'Weather','version':'0.9.0','kind':'weather','description':'Weather','author':'Psychnix','license':'MIT','script':'x'}))

@case('unlisted weather package at the wrong path',False,'path must be cleantv-packages/<id>/<version>.json')
def _(f):
    file=f.root/'cleantv-packages'/'cleantv-weather'/'0.9.0.json';file.parent.mkdir(parents=True)
    file.write_bytes(dump({'api':1,'id':'cleantv-weather','name':'Weather','version':'0.8.0','kind':'weather','description':'Weather','author':'Psychnix','license':'MIT'}))

@case('unlisted weather package over the host limit',False,'cleantv-packages/cleantv-weather/0.9.0.json: description exceeds 240')
def _(f):
    file=f.root/'cleantv-packages'/'cleantv-weather'/'0.9.0.json';file.parent.mkdir(parents=True)
    file.write_bytes(dump({'api':1,'id':'cleantv-weather','name':'Weather','version':'0.9.0','kind':'weather','description':EMOJI*121,'author':'Psychnix','license':'MIT'}))

def main():
    failures=0
    with tempfile.TemporaryDirectory(prefix='cleantv-validate-') as temp:
        base=Path(temp)/'base'
        copy_inputs(base)
        for index,(name,change,passes,expect) in enumerate(CASES):
            root=Path(temp)/f'case{index}'
            shutil.copytree(base,root)
            change(Fixture(root))
            result=subprocess.run([sys.executable,str(root/'scripts'/'validate.py')],cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace',env=dict(os.environ,PYTHONUTF8='1'))
            output=result.stdout+result.stderr
            ok=(result.returncode==0)==passes and expect in output
            if passes and 'CleanTV catalog, checksums and packages validated.' not in output:ok=False
            print(('ok   ' if ok else 'FAIL ')+name)
            if not ok:
                failures+=1
                print('     exit',result.returncode,'expected',('pass' if passes else 'failure containing '+repr(expect)))
                print('     '+output.strip().replace('\n','\n     ')[-1500:])
    print(f'{len(CASES)-failures}/{len(CASES)} CleanTV validator cases passed.')
    return 1 if failures else 0

if __name__=='__main__':sys.exit(main())
