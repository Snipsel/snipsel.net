#!/usr/bin/env python3
from pathlib import Path
import boto3

def main():
    s3 = authenticate()
    objects = list_objects(s3)
    for k,v in objects.items():
        print(f'{k}: {v}')

def authenticate():
    secrets_path =  Path(__file__).parent/".secrets"
    return boto3.client('s3',
        aws_access_key_id = (secrets_path/'access_key_id').read_text(encoding='utf-8').strip(),
        aws_secret_access_key = (secrets_path/'access_key').read_text(encoding='utf-8').strip(),
        endpoint_url = f"https://{(secrets_path/'account_id').read_text(encoding='utf-8').strip()}.r2.cloudflarestorage.com",
        region_name = 'auto')

def list_objects(s3):
    response = s3.list_objects_v2(Bucket='www')
    if response['IsTruncated']:
        print('truncated list not yet supported')
        return 1
    files = {}
    for o in response['Contents']:
        key = o['Key']
        o.pop('Key')
        files[key] = o
    return files

    print(files)


if __name__ == "__main__":
    main()

