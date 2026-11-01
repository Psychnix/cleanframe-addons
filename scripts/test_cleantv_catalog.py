"""Regression tests for the CleanTV section of scripts/validate.py.

Each case copies the validation inputs into a temporary directory, changes the
CleanTV catalog or its packages and runs the real validate.py there. The cases
cover gaps where validate.py once passed a catalog that the Samsung host rejects
for every TV (UTF-16 lengths, non-UTF-8 encodings) or could never accept a valid
package (weather and wallpapers outside the upstream packages/ directory).
Every case runs twice: on the committed tree and on one whose committed
wallpaper index already lists a generated wallpaper, as after the generator's
first commit.
"""
import hashlib,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path

repo=Path(__file__).resolve().parents[1]
INPUTS=['catalog.json','catalog-v2.json','catalog-v2.schema.json','native-package.schema.json','package.schema.json','cleantv-catalog.json','cleantv-catalog.schema.json','cleantv-wallpapers/index.json','cleantv-wallpapers/index.schema.json']
# validate.py never reads cleantv-wallpapers/images/ (originals up to 30 MB each) or tools/, so the cases copy neither.
FOLDERS=['packages','examples','cleantv-packages','cleantv-wallpapers/generated']
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
        self._wallpapers_reset=False
    def reset_wallpapers(self):
        """Remove the committed generated/ files once, before the case writes its own wallpaper index."""
        if not self._wallpapers_reset:
            shutil.rmtree(self.root/'cleantv-wallpapers'/'generated',ignore_errors=True)
            self._wallpapers_reset=True
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
        # The catalog already lists cleantv-weather; a case's own entry replaces the listed one.
        self.catalog['addons']=[other for other in self.catalog['addons'] if other['id']!=entry['id']]
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

def without_wallpapers(fixture):
    # The committed catalog lists the wallpapers package; cases that add their own entry start without it.
    fixture.catalog['addons']=[entry for entry in fixture.catalog['addons'] if entry['kind']!='wallpapers']

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
    without_wallpapers(f);f.add(wallpapers());f.save()

@case('weather and wallpapers together',True)
def _(f):
    without_wallpapers(f);f.add(weather());f.add(wallpapers());f.save()

@case('the listed weather package (exact bytes, CleanTV path)',True)
def _(f):
    entry=f.entry('cleantv-weather')
    assert entry['path']=='cleantv-packages/cleantv-weather/1.0.0.json' and entry['kind']=='weather'

@case('weather entry with another id, which the host refuses',False,'ValidationError')
def _(f):
    f.add(weather(id='weather-two',path='cleantv-packages/weather-two/1.0.0.json'));f.save()

@case('listed weather entry with an extra field',False,'ValidationError')
def _(f):
    f.add(weather(script='alert(1)'));f.save()

@case('unlisted weather package with another id',False,'ValidationError')
def _(f):
    file=f.root/'cleantv-packages'/'weather-two'/'1.0.0.json';file.parent.mkdir(parents=True,exist_ok=True)
    file.write_bytes(dump({'api':1,'id':'weather-two','name':'Weather','version':'1.0.0','kind':'weather','description':'Weather','author':'Psychnix','license':'MIT'}))

@case('wallpapers entry with another id, which the host module ignores',False,'ValidationError')
def _(f):
    f.add(dict(f.entry('cleantv-wallpapers'),id='wallpapers-two',path='cleantv-packages/wallpapers-two/1.0.0.json'));f.save()

@case('unlisted wallpapers package with another id',False,"'cleantv-wallpapers' was expected")
def _(f):
    file=f.root/'cleantv-packages'/'wallpapers-two'/'1.0.0.json';file.parent.mkdir(parents=True,exist_ok=True)
    file.write_bytes(dump({'api':1,'id':'wallpapers-two','name':'Wallpapers','version':'1.0.0','kind':'wallpapers','description':'Wallpapers','author':'Psychnix','license':'MIT','index':'cleantv-wallpapers/index.json'}))

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
    file=f.root/'cleantv-packages'/'cleantv-note'/'1.0.0.json';file.parent.mkdir(parents=True,exist_ok=True)
    file.write_bytes(dump({'api':1,'id':'cleantv-note','name':'Note','version':'1.0.0','kind':'text','description':'Note','author':'Psychnix','license':'MIT'}))

@case('unlisted weather package with an extra field',False,'ValidationError')
def _(f):
    file=f.root/'cleantv-packages'/'cleantv-weather'/'0.9.0.json';file.parent.mkdir(parents=True,exist_ok=True)
    file.write_bytes(dump({'api':1,'id':'cleantv-weather','name':'Weather','version':'0.9.0','kind':'weather','description':'Weather','author':'Psychnix','license':'MIT','script':'x'}))

@case('unlisted weather package at the wrong path',False,'path must be cleantv-packages/<id>/<version>.json')
def _(f):
    file=f.root/'cleantv-packages'/'cleantv-weather'/'0.9.0.json';file.parent.mkdir(parents=True,exist_ok=True)
    file.write_bytes(dump({'api':1,'id':'cleantv-weather','name':'Weather','version':'0.8.0','kind':'weather','description':'Weather','author':'Psychnix','license':'MIT'}))

@case('unlisted weather package over the host limit',False,'cleantv-packages/cleantv-weather/0.9.0.json: description exceeds 240')
def _(f):
    file=f.root/'cleantv-packages'/'cleantv-weather'/'0.9.0.json';file.parent.mkdir(parents=True,exist_ok=True)
    file.write_bytes(dump({'api':1,'id':'cleantv-weather','name':'Weather','version':'0.9.0','kind':'weather','description':EMOJI*121,'author':'Psychnix','license':'MIT'}))

# ---------- Wallpaper index (cleantv-wallpapers/index.json) ----------
WALLPAPER_FILES={'jpg':'image.jpg','thumb':'thumb.jpg','panel':'panel.jpg','study-soft':'study-soft.jpg','field-blur':'field-blur.jpg','field-frost':'field-frost.jpg','field-clear':'field-clear.jpg'}

def wallpaper(f,wid='aw-berg',title='Berg',**extra):
    """Write seven stand-in files for one entry (validate.py checks bytes, not pixels) and return the entry."""
    f.reset_wallpapers()  # wallpaper() runs before save_index(), so the first of the two clears generated/
    files={}
    for role,name in WALLPAPER_FILES.items():
        data=(wid+'/'+role).encode('ascii')*8
        path=f'cleantv-wallpapers/generated/{wid}/{name}'
        target=f.root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        files[role]={'path':path,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    entry={'id':wid,'title':title,'rev':files['jpg']['sha256'][:12],'tone':'light','ut':{'tr':'mist','br':'light'},'frostVeil':0.2,'files':files}
    entry.update(extra)
    return entry

def save_index(f,entries,data=None):
    f.reset_wallpapers()
    body=json.dumps({'api':1,'entries':entries},ensure_ascii=False,separators=(',',':'))+'\n'
    (f.root/'cleantv-wallpapers'/'index.json').write_bytes(body.encode('utf-8') if data is None else data)

@case('wallpaper index with two generated entries',True)
def _(f):save_index(f,[wallpaper(f),wallpaper(f,'aw-see','See',listColumn=3,dockQuiet=True,clockMist=True)])

@case('wallpapers package without its index',False,'cleantv-wallpapers/index.json: missing')
def _(f):(f.root/'cleantv-wallpapers'/'index.json').unlink()

@case('wallpaper file whose bytes changed',False,'aw-berg: sha256 does not match the bytes of cleantv-wallpapers/generated/aw-berg/thumb.jpg')
def _(f):
    entry=wallpaper(f);save_index(f,[entry]);path=f.root/entry['files']['thumb']['path'];data=bytearray(path.read_bytes());data[0]^=1;path.write_bytes(bytes(data))

@case('wallpaper file with another size',False,'aw-berg: cleantv-wallpapers/generated/aw-berg/panel.jpg has')
def _(f):
    entry=wallpaper(f);entry['files']['panel']['size']+=1;save_index(f,[entry])

@case('missing wallpaper file',False,'aw-berg: cleantv-wallpapers/generated/aw-berg/field-clear.jpg does not exist')
def _(f):
    entry=wallpaper(f);save_index(f,[entry]);(f.root/entry['files']['field-clear']['path']).unlink()

@case('duplicate wallpaper id',False,'duplicate id aw-berg')
def _(f):save_index(f,[wallpaper(f),wallpaper(f)])

@case('wallpaper file in the folder of another id',False,'aw-see: the jpg path must be cleantv-wallpapers/generated/aw-see/image.jpg')
def _(f):
    first=wallpaper(f);second=wallpaper(f,'aw-see','See');second['files']['jpg']=first['files']['jpg'];second['rev']=first['rev'];save_index(f,[first,second])

@case('wallpaper rev that is not the jpg checksum',False,'aw-berg: rev must be the first 12 hex digits')
def _(f):save_index(f,[wallpaper(f,rev='0'*12)])

@case('generated file that no entry references',False,'files in generated/ that no entry references: cleantv-wallpapers/generated/aw-alt/image.jpg')
def _(f):
    entry=wallpaper(f);save_index(f,[entry]);stray=f.root/'cleantv-wallpapers'/'generated'/'aw-alt'/'image.jpg';stray.parent.mkdir(parents=True);stray.write_bytes(b'old')

@case('wallpaper index with 201 entries',False,'ValidationError')
def _(f):
    entry=wallpaper(f);save_index(f,[dict(entry,id='aw-x'+str(n)) for n in range(201)])

@case('wallpaper index over 262144 bytes',False,'bytes exceeds 262144')
def _(f):save_index(f,[],(json.dumps({'api':1,'entries':[]})+' '*262144).encode('utf-8'))

@case('wallpaper title of 60 astral characters is exactly 120 UTF-16 units',True)
def _(f):save_index(f,[wallpaper(f,title=EMOJI*60)])

@case('wallpaper title of 61 astral characters is 122 UTF-16 units',False,'aw-berg: title exceeds 120 UTF-16 code units')
def _(f):save_index(f,[wallpaper(f,title=EMOJI*61)])

@case('wallpaper frost veil outside the five veil classes',False,'ValidationError')
def _(f):save_index(f,[wallpaper(f,frostVeil=0.25)])

@case('wallpaper listColumn given as true',False,'ValidationError')
def _(f):save_index(f,[wallpaper(f,listColumn=True)])

@case('wallpaper entry with an unknown field',False,'ValidationError')
def _(f):save_index(f,[wallpaper(f,script='x')])

@case('wallpaper id with a capital letter',False,'ValidationError')
def _(f):save_index(f,[wallpaper(f,'aw-Berg')])

@case('wallpaper panel over its size limit',False,'aw-berg: panel exceeds 65536 bytes')
def _(f):
    entry=wallpaper(f);path=f.root/entry['files']['panel']['path'];data=b'p'*65537;path.write_bytes(data)
    entry['files']['panel'].update(size=len(data),sha256=hashlib.sha256(data).hexdigest());save_index(f,[entry])

@case('wallpaper index encoded as UTF-16',False,'cleantv-wallpapers/index.json: must be UTF-8 JSON')
def _(f):save_index(f,[],json.dumps({'api':1,'entries':[]}).encode('utf-16'))

def committed_wallpaper(f):
    # After the generator's first bot commit the committed index is not empty; aw-abend sorts before the stray aw-alt above.
    save_index(f,[wallpaper(f,'aw-abend','Abend')])

# Every case runs on the committed tree and again on one whose committed index already lists a generated wallpaper.
PASSES=[('committed tree',None),('committed tree with one generated wallpaper',committed_wallpaper)]

def main():
    failures=0
    with tempfile.TemporaryDirectory(prefix='cleantv-validate-') as temp:
        for number,(label,seed) in enumerate(PASSES):
            print('-- '+label)
            base=Path(temp)/f'base{number}'
            copy_inputs(base)
            if seed:seed(Fixture(base))
            for index,(name,change,passes,expect) in enumerate(CASES):
                root=Path(temp)/f'case{number}-{index}'
                shutil.copytree(base,root)
                change(Fixture(root))
                result=subprocess.run([sys.executable,str(root/'scripts'/'validate.py')],cwd=root,capture_output=True,text=True,encoding='utf-8',errors='replace',env=dict(os.environ,PYTHONUTF8='1'))
                output=result.stdout+result.stderr
                ok=(result.returncode==0)==passes and expect in output
                if passes and 'CleanTV catalog, checksums and packages validated.' not in output:ok=False
                # validate.py never reads the originals (up to 30 MB each), so no case tree may hold a copy.
                if (root/'cleantv-wallpapers'/'images').exists():ok=False;output+='\ncleantv-wallpapers/images/ was copied into the case'
                print(('ok   ' if ok else 'FAIL ')+name)
                if not ok:
                    failures+=1
                    print('     exit',result.returncode,'expected',('pass' if passes else 'failure containing '+repr(expect)))
                    print('     '+output.strip().replace('\n','\n     ')[-1500:])
                shutil.rmtree(root,ignore_errors=True)  # at most the base and one case tree on disk
            shutil.rmtree(base,ignore_errors=True)
    total=len(PASSES)*len(CASES)
    print(f'{total-failures}/{total} CleanTV validator cases passed.')
    return 1 if failures else 0

if __name__=='__main__':sys.exit(main())
