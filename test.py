#!/usr/bin/env python3
from sys import exit
import requests
from bs4 import BeautifulSoup

def main():
    index_html = requests.get('https://snipsel.net')
    if index_html.status_code != 200: exit("index_html not 200")
    soup = BeautifulSoup(index_html.text, 'html.parser')

    thumbs = get_thumbs(soup)
    print(f"checking {len(thumbs)} thumbnails")
    failed_thumbs = []
    for thumb in thumbs:
        if requests.head(f'https://snipsel.net/{thumb}').status_code != 200:
            failed_thumbs.append(thumb)

    if len(failed_thumbs)==0:
        print("thumbnails OK")
    else:
        print("failed thumbs:")
        for thumb in failed_thumbs:
            print(thumb)

    internal, external = get_links(soup)

    print(f'testing {len(internal)} internal links')
    failed_internal_links = []
    for link in internal:
        link = f'https://snipsel.net/{link}'
        req = requests.head(link)
        print(f'{req.status_code} {link}')
        if req.status_code != 200:
            failed_internal_links.append(link)
    if len(failed_internal_links)==0:
        print("internal links OK")
    else:
        print("failed internal links:")
        for link in failed_internal_links:
            print(link)

    print(f'testing {len(external)} external links')
    failed_external_links = []
    for link in external:
        req = requests.head(link)
        print(f'{req.status_code} {link}')
        if requests.head(link).status_code == 404:
            failed_external_links.append(link)
    if len(failed_external_links)==0:
        print("external links probably OK")
    else:
        print("failed external links:")
        for link in failed_external_links:
            print(link)

def get_thumbs(soup):
    thumbs = []
    for source in soup.find_all('source'):
        for imgsrc in source['srcset'].split(','):
            thumbs.append(imgsrc.split(' ')[0])
    return list(set(thumbs))

def get_links(soup):
    external = []
    internal = []
    for anchor in soup.find_all('a'):
        href = anchor['href']
        if href.startswith('https://'):
            external.append(href)
        else:
            internal.append(href)
    return list(set(internal)),list(set(external))

if __name__ == '__main__':
    main()
