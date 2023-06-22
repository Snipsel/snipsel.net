#!/usr/bin/env python3
from pathlib import Path
from hashlib import sha3_256
from base64  import urlsafe_b64encode, urlsafe_b64decode
from sys import exit
from math import ceil
import boto3

local_path = Path(__file__).parent/"www"

def main():
    s3 = authenticate()
    objects = list_objects(s3)

    max_filename_len = max([len(key) for key in objects])

    for file in local_path.iterdir():
        fname = (ceil(max_filename_len/2)*'· ')[:max_filename_len]
        fname = file.name + fname[len(file.name):] + ' '
        warn = '⚠️'+'\033[4G'+fname
        upld = '⬆️'+'\033[4G'+fname
        keep = '✅'+'\033[4G'+fname
        if not file.is_file(): 
            print(f'{warn}not a file -> skipping')
        elif file.name not in objects:
            print(f'{upld}not on remote -> uploading')
            put_object(s3, file)
        elif file.stat().st_size != objects[file.name]['Size']:
            print(f'{upld}different size on remote -> uploading')
            put_object(s3, file)
        else:
            head = s3.head_object(Bucket='www', Key=file.name)
            if 'sha3-256' not in head['Metadata']:
                print(f'{upld}missing sha3-256 hash -> uploading')
                put_object(s3, file)
            elif hash(file.read_bytes()) != head['Metadata']['sha3-256']:
                print(f'{upld}hash mismatch -> uploading')
                put_object(s3, file)
            else:
                print(f'{keep}hash matches -> skipping')

def authenticate():
    secrets_path =  Path(__file__).parent/".secrets"
    return boto3.client('s3',
        aws_access_key_id = (secrets_path/'access_key_id').read_text(encoding='utf-8').strip(),
        aws_secret_access_key = (secrets_path/'access_key').read_text(encoding='utf-8').strip(),
        endpoint_url = f"https://{(secrets_path/'account_id').read_text(encoding='utf-8').strip()}.r2.cloudflarestorage.com",
        region_name = 'auto')

def list_objects(s3):
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
    response = s3.put_object(
        Key=filepath.name,
        Body=file_bytes,
        Bucket='www',
        Metadata={
            'sha3-256': hash(file_bytes)
        })
    
if __name__ == "__main__":
    main()

