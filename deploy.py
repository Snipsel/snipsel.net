#!/usr/bin/env python3
from pathlib import Path
from hashlib import sha3_256
from base64  import urlsafe_b64encode, urlsafe_b64decode
from sys import exit
from math import ceil
import boto3

local_path = Path(__file__).parent/"www"

def sync(skip_thumbs:bool=False):
    s3 = authenticate()

    objects = list_objects(s3)
    local_files = list(local_path.iterdir())

    if skip_thumbs:
        def is_thumb(s:str):
            return s.endswith('.jpg') or s.endswith('.avif')
        objects     = {k:v for k,v in objects.items() if not is_thumb(k)}
        local_files = [f   for f   in local_files     if not is_thumb(f.name)]

    local_file_names = [str(p.name) for p in local_files]
    max_filename_len = max([len(p) for p in list(objects.keys())+local_file_names])

    for file in local_files:
        pending = lambda msg,act: print_pending(file.name, max_filename_len, msg, act)
        if not file.is_file(): 
            print_message(sym_warning, 'not a file', 'skipped')
        elif file.name not in objects:
            pending('not on remote','uploading')
            put_object(s3, file)
            print_done(sym_upload,'uploaded')
        elif file.stat().st_size != objects[file.name]['Size']:
            pending('different size on remote', 'uploading')
            put_object(s3, file)
            print_done(sym_upload,'uploaded')
        else:
            head = head_object(s3, file)
            if 'sha3-256' not in head['Metadata']:
                pending('missing sha3-256 hash','uploading')
                put_object(s3, file)
                print_done(sym_upload,'uploaded')
            elif hash(file.read_bytes()) != head['Metadata']['sha3-256']:
                pending('hash mismatch','uploading')
                put_object(s3, file)
                print_done('sym_upload','done')
            else:
                print_message(sym_skip,'hash matches','skipped')

    extra_remote_files = list(set(objects.keys()) - set(local_file_names))
    if len(extra_remote_files) == 0:
        print_message(sym_clean, 'remote is clean', 'skipped')
    else:
        st = []
        pending('remote not clean','deleting')
        delete_objects(s3, extra_remote_files)
        print_done(sym_delete,'deleted')

    print_opcount()

def push(local_files:list[str]):
    s3 = authenticate()
    max_len = max([len(f) for f in local_files])
    for file in local_files:
        print_pending(file, max_len, 'pushed unconditionally','uploading')
        put_object(s3, local_path/file)
        print_done(sym_upload,'uploaded')
    print_opcount()

def authenticate():
    secrets_path =  Path(__file__).parent/".secrets"
    return boto3.client('s3',
        aws_access_key_id = (secrets_path/'access_key_id').read_text(encoding='utf-8').strip(),
        aws_secret_access_key = (secrets_path/'access_key').read_text(encoding='utf-8').strip(),
        endpoint_url = f"https://{(secrets_path/'account_id').read_text(encoding='utf-8').strip()}.r2.cloudflarestorage.com",
        region_name = 'auto')

def head_object(s3, file:Path):
    inc_opcount('headObject','B')
    return s3.head_object(Bucket='www', Key=file.name)

def delete_objects(s3, names:list[str]):
    if len(names) > 0:
        inc_opcount('deleteObjects','0')
        s3.delete_objects(
            Bucket='www',
            Delete={
                'Objects': [{'Key':n} for n in names],
                'Quiet': True })

def list_objects(s3):
    inc_opcount('listObjectsV2','A')
    response = s3.list_objects_v2(Bucket='www')
    if response['IsTruncated']: exit('truncated listObjectsV2 response not yet supported')
    files = {}
    for o in response['Contents']:
        key = o['Key']
        o.pop('Key')
        files[key] = o
    return files

def hash(file_bytes:bytes):
    return urlsafe_b64encode(sha3_256(file_bytes).digest()).decode('ascii')

def put_object(s3, filepath:Path):
    file_bytes = filepath.read_bytes()
    inc_opcount('putObject','A')
    s3.put_object(
        Key=filepath.name,
        Body=file_bytes,
        Bucket='www',
        Metadata={
            'sha3-256': hash(file_bytes)
        })

opcount = { }

def inc_opcount(op:str, opclass:str):
    idx = {'A':0,'B':1,'0':2}[opclass];
    if op not in opcount:
        opcount[op] = [0,0,0]
    opcount[op][idx] += 1

def boxify(lines:list[str]):
    wid = len(lines[0])
    ret = []
    ret.append('╭─' + wid*'─'  + '─╮')
    ret.append('│ ' + lines[0] + ' │')
    ret.append('├╶' + wid*'╶'  + '╶│')
    for line in lines[1:-1]:
        ret.append('│ ' + line + ' │')
    ret.append('├╶' + wid*'╶'  + '╶│')
    ret.append('│ ' + lines[-1]+ ' │')
    ret.append('╰─' + wid*'─'  + '─╯')
    return ret

def pad_with_dots(s:str, max_len:int):
    dots = (ceil(max_len/2)*'· ')[:max_len]
    return s + dots[len(s):] + ' '

def csi(*args:str) -> str:
    return ''.join(['\033['+arg for arg in args])
def bold(text:str) -> str:
    return csi('93;1m')+text+csi('0m')
def italic(text:str) -> str:
    return csi('3m')+text+csi('0m')
def column(c:int):
    if(c<=1): return csi('99D')
    else: return csi('99D',f'{int(c)}C')

maxlen_action = len('uploading')
sym_pending = '\u23F3'
sym_warning = '\u26A0\uFE0F'
sym_upload  = '\u2B06\uFE0F'
sym_skip    = '\u23ED\uFE0F'
sym_delete  = '\U0001F6AE'
sym_clean   = '\u2728'
sym_failed  = '\u274C'

def print_pending(name:str, maxlen:int, msg:str, action:str):
    print( sym_pending + column(3) + 
           italic(action.ljust(maxlen_action+1)) +
           pad_with_dots(name,maxlen) +
           italic(msg),
           end='', flush=True)

def print_done(symbol:str, action:str):
    print(column(maxlen_action+3) + csi('1K') + column(0) + symbol + column(3) + bold(action.ljust(maxlen_action)))

def print_message(symbol:str, msg:str, action:str=''):
    print(symbol + column(3) + bold(action.ljust(maxlen_action+1)) + msg)

def print_opcount():
    max_op_len = max([len(key) for key in opcount])
    lines = []
    lines.append('op'.ljust(max_op_len) + '    A    B    0')
    total = [0,0,0]
    for k,v in opcount.items():
        line = k.ljust(max_op_len)
        for i,n in enumerate(v):
            line += '    ·' if n==0 else f'{n:>5}'
            total[i] += n
        lines.append(line)
    line = 'total'.ljust(max_op_len)
    for t in total:
        line += f'{t:>5}'
    lines.append(line);
    print('\n'.join(boxify(lines)))

if __name__ == "__main__":
    from sys import argv
    try:
        if '-h' in set(argv[1:]) or '--help' in set(argv[1:]):
            print(f"{bold(argv[0])} {italic('[--skip-thumbs]')}")
            print(f"    Syncs the remote to be identical to local.")
            print(f"    {bold('--skip-thumbs')}  Skip thumbnails.")
            print(f"{bold(argv[0]+' push')} {italic('[files...]')}")
            print(f"    Pushes local files to remote unconditionally.")
        elif argv[1] == 'push':
            push(argv[2:])
        else:
            argset = set(argv[1:])
            sync(skip_thumbs=('--skip-thumbs' in argset))
    except KeyboardInterrupt:
        exit('\ninterrupted')

