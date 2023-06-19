#!/usr/bin/env python3
import yaml
from pathlib import Path
from shutil import copy,rmtree
from wand.image import Image
from math import floor
import subprocess

src_path = Path(__file__).parent/"src"
dst_path = Path(__file__).parent/"www"
img_path = Path(__file__).parent/"img"
data_path =  Path(__file__).parent/"data"

skip_images = True

def main():
    if not skip_images:
        rmtree(dst_path, ignore_errors=True)
    dst_path.mkdir(parents=True, exist_ok=True)
    copy(data_path/"favicon32.png", dst_path)
    copy(data_path/"Nunito.ttf", dst_path/"nunito.ttf")
    artworks, artists, pfp_path, refsheet_path = get_images()

    gallery_html = []
    refsheet_html = ""
    pfp_html = ""
    for path,artwork in artworks.items():
        if path==pfp_path:
            pfp_html = gen_html_pfp(**artwork)
            gallery_html.append(gen_html_figure(**artwork))
        elif path==refsheet_path:
            refsheet_html = gen_html_figure(**artwork)
        else:
            gallery_html.append(gen_html_figure(**artwork))

    write_txt("index.html",
              resolve(strip_lines(read_txt("index.html")), 
                   title="Snipsel's Cozy Corner of the Internet",
                   style=strip_lines(read_txt("style.css")+read_txt("profile.css")+read_txt("gallery.css")),
                   svg=strip_lines(read_txt("icons.svg")),
                   pfp=strip_lines(pfp_html),
                   refsheet=strip_lines(refsheet_html),
                   gallery=strip_lines(''.join(gallery_html)),
                   githash=git_short_hash() ))

def git_short_hash() -> str:
    return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip().upper()

def gen_artist_links(artist:dict) -> str:
    html = ""
    for kind,link in artist['links'].items():
        html += f"""
            <a href="{link}">
                <svg>
                    <use href="#icon-{kind}"/>
                </svg>
            </a>"""
    return html

def gen_html_picture(artist:dict, slug:str, size, thumbs:list, date:str, alt:str, edits:dict[str,str]={}):
    mini_jpg  = ','.join([f'{slug}-{w}w.jpg {w}w' for w,h in thumbs])
    mini_avif = ','.join([f'{slug}-{w}w.avif {w}w' for w,h in thumbs])
    return f"""
          <picture>
            <source type="image/avif" sizes="calc(100% - 2rem)" srcset="{mini_avif}">
            <source type="image/jpeg" sizes="calc(100% - 2rem)" srcset="{mini_jpg}">
            <img src="{slug}-400w.jpg" alt="{alt}">
          </picture>"""

def gen_html_figure(artist:dict, slug:str, size, thumbs:list, date:str, alt:str, edits:dict[str,str]={}) -> str:
    yyyy,mm,dd = date.split(' ')[0].split('-')
    month = [None, "Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][int(mm)]
    return f"""
        <figure id="{slug}" class="artwork">
          <a href="{slug}">
            {gen_html_picture(artist=artist, slug=slug, size=size, thumbs=thumbs, date=date, alt=alt)}
          </a>
          <figcaption>
            {artist['name']}
            {gen_artist_links(artist)}
            <time datetime="{date}">{month} {yyyy}</time>
          </figcaption>
        </figure>"""

def gen_html_pfp(artist:dict, slug:str, size, thumbs:list, date:str, alt:str, edits:dict[str,str]={}) -> str:
    return f"""
        <figure id="pfp" class="artwork">
          {gen_html_picture(artist=artist, slug=slug, size=size, thumbs=thumbs, date=date, alt=alt)}
        </figure>"""

def get_images():
    def interleave(outer:list[str], inner:list[str]):
        if not len(inner) == (len(outer)-1):
            raise Exception("interleave failed: outer list not 1 element longer than inner list")
        ret = outer[0]
        for i in range(len(inner)):
            ret += inner[i]
            ret += outer[i+1]
        return ret

    def resolve_links(artists, link_templates):
        ret = {}
        for artist_id, artist in artists.items():
            d = {}
            for key,value in artist.items():
                if key=='links':
                    d['links'] = {}
                    for key,value in artist['links'].items():
                        if key in link_templates:
                            d['links'][key] = interleave(link_templates[key].split('$'), value.split(' '))
                        else:
                            Exception(f"unknown link format: {key}")
                else:
                    d[key] = value
            ret[artist_id] = d
        return ret

    def load_metadata(metadata:list):
        artworks, artists_unlinked, config = metadata
        artists = resolve_links(artists_unlinked, config['link_templates'])
        return artworks, artists, config['pfp'], config['refsheet']

    def slugify_filename(filename: str):
        slug = str(str(Path(filename).stem))
        slug = slug.replace('snipsel','')
        slug = slug.replace('--','')
        slug = slug.strip('-')
        return slug

    def generate_thumb(slug:str, w:int, h:int):
        if not skip_images:
            print(f"{slug}: {w}x{h}")
            with source_img.clone() as o:
                o.thumbnail(width=w, height=h)
                o.compression_quality=64 # may be too low?
                o.save(filename=dst_path/(slug + f'-{w}w.avif'))
            with source_img.clone() as o:
                o.thumbnail(width=w, height=h)
                o.compression_quality=80
                o.save(filename=dst_path/(slug + f'-{w}w.jpg'))

    with open(img_path/'metadata.yaml', 'r') as file:
        artworks, artists, pfp, refsheet = load_metadata(list(yaml.safe_load_all(file)))

    for path,artwork in artworks.items():
        artist_id, slug = path.split('/')
        artwork['artist'] = artists[artist_id]
        slug = slugify_filename(slug) + '-by-' + artist_id;
        artwork['slug'] = slug
        artwork['thumbs'] = []
        with Image(filename=img_path/path) as source_img:
            artwork['size'] = (source_img.width, source_img.height)
            for w_exp in range(100):
                w = int(round(200*2**(floor(w_exp/2))*(1+0.5*(w_exp%2))))
                if w>=source_img.width: break;
                h = int(round( (w/source_img.width) * source_img.height ))
                artwork['thumbs'].append( (w,h) )
                generate_thumb(slug, w, h)
            generate_thumb(slug, source_img.width, source_img.height)
        copy(img_path/path, dst_path/slug)
    return artworks, artists, pfp, refsheet

def read_txt(filename:str):
    return (src_path/filename).read_text(encoding="utf-8")

def write_txt(filename:str, text:str):
    (dst_path/filename).write_text(text, encoding="utf-8")

def resolve(template:str, **replacements: dict[str,str]):
    for tag,repl in replacements.items():
        template = template.replace('{'+tag+'}', repl);
    return template

def strip_lines(s:str):
    return ''.join(map(lambda x: x.strip(), s.splitlines()))

if __name__ == "__main__":
    main()
