#!/usr/bin/env python3
import yaml
from pathlib import Path
from shutil import copy,rmtree
from wand.image import Image
from math import floor
import subprocess
from fontTools import subset
from dataclasses import dataclass
from enum import Enum, unique
from typing import Iterator

src_path  = Path(__file__).parent/"src"
dst_path  = Path(__file__).parent/"www"
img_path  = Path(__file__).parent/"img"
data_path =  Path(__file__).parent/"data"

def main():
    skip_images = False
    if not skip_images:
        rmtree(dst_path, ignore_errors=True)
    dst_path.mkdir(parents=True, exist_ok=True)
    copy(data_path/"favicon32.png", dst_path)
    subset_font(str(data_path/"Nunito.ttf"), str(dst_path/"nunito.woff2"))
    artworks = load_artworks(src_path/'metadata.yaml',
                             copy_images=not skip_images,
                             gen_thumbs =not skip_images)
    #artworks = dict(sorted(artworks.items(), reverse=True, key=lambda e: e[1]['date']))

    gallery_html = []
    refsheet_html = ""
    pfp_html = ""
    for artwork in artworks:
        if artwork.category==ArtworkCategory.pfp:
            pfp_html = gen_html_pfp(artwork)
            gallery_html.append(gen_html_figure(artwork))
        elif artwork.category==ArtworkCategory.refsheet:
            refsheet_html = gen_html_figure(artwork)
        else:
            gallery_html.append(gen_html_figure(artwork))

    write_txt("index.html",
              resolve(strip_lines(read_txt("index.html")), 
                   title="Snipsel's Cozy Corner of the Internet",
                   style=strip_lines(read_txt("style.css")+read_txt("profile.css")+read_txt("gallery.css")),
                   svg=strip_lines(read_txt("icons.svg")),
                   pfp=strip_lines(pfp_html),
                   refsheet=strip_lines(refsheet_html),
                   gallery=strip_lines(''.join(gallery_html)),
                   githash=git_short_hash() ))

@dataclass(slots=True)
class Extent:
    w: int
    h: int

@unique
class ArtworkCategory(Enum):
    regular  = 0
    refsheet = 1
    pfp      = 2
    def match(self,pfp,refsheet,regular):
        match self:
            case ArtworkCategory.pfp:      return pfp
            case ArtworkCategory.refsheet: return refsheet
            case ArtworkCategory.regular:  return regular
            case _: raise ValueError("unrecognised artwork category")

@dataclass(slots=True)
class Artwork:
    artist : dict
    slug : str
    size : Extent
    thumbs : list[Extent]
    date : str
    alt : str
    sha3 : str
    category : ArtworkCategory

def git_short_hash() -> str:
    return subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).decode('ascii').strip().upper()

def subset_font(infont:str, outfont:str):
    subset.main([
        infont,
        '--flavor=woff2',
       f'--output-file={outfont}',
        '--layout-features=kern,liga,onum',
        '--desubroutinize',
        '--no-hinting',
        '--text="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz@_!,’"'])

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

def gen_html_picture(art:Artwork):
    sizes = art.category.match(
        pfp      = 'min(100vw,calc(320px - 2rem))',
        refsheet = 'min(100vw,calc(800px - 2rem))',
        regular  = 'min(100vw,50vh)')
    mini_jpg  = ','.join([f'{art.slug}-{e.w}w.jpg {e.w}w' for e in art.thumbs])
    mini_avif = ','.join([f'{art.slug}-{e.w}w.avif {e.w}w' for e in art.thumbs])

    return f"""
        <picture>
          <source type="image/avif" sizes="{sizes}" srcset="{mini_avif}">
          <source type="image/jpeg" sizes="{sizes}" srcset="{mini_jpg}">
          <img width="{art.size.w}" height="{art.size.h}" src="{art.slug}-400w.jpg" alt="{art.alt}">
        </picture>"""

def gen_html_figure(art:Artwork) -> str:
    yyyy,mm,dd = art.date.split(' ')[0].split('-')
    month = [None, "Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][int(mm)]
    return f"""
        <figure id="{art.slug}" class="artwork">
          <a href="{art.slug}">
            {gen_html_picture(art)}
          </a>
          <figcaption>
            {art.artist['name']}
            {gen_artist_links(art.artist)}
            <time datetime="{art.date}">{month} {yyyy}</time>
          </figcaption>
        </figure>"""

def gen_html_pfp(art:Artwork) -> str:
    return f"""
        <figure id="pfp" class="artwork">
          {gen_html_picture(art)}
        </figure>"""


def load_artworks(yaml_path:Path, copy_images:bool, gen_thumbs:bool) -> list[Artwork]:
    def interleave(outer:list[str], inner:list[str]) -> list[str]:
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

    def thumb_sizes(w:int,h:int) -> Iterator[Extent]:
        for w_exp in range(100):
            w = int(round(200*2**(floor(w_exp/2))*(1+0.5*(w_exp%2))))
            if w>=source_img.width: break;
            h = int(round( (w/source_img.width) * source_img.height ))
            yield Extent(w,h)

    def generate_thumb(slug:str, w:int, h:int) -> None:
        print(f"{slug}: {w}x{h}")
        with source_img.clone() as o:
            o.thumbnail(width=w, height=h)
            o.compression_quality=64 # may be too low?
            o.save(filename=dst_path/(slug + f'-{w}w.avif'))
        with source_img.clone() as o:
            o.thumbnail(width=w, height=h)
            o.compression_quality=80
            o.save(filename=dst_path/(slug + f'-{w}w.jpg'))

    def categorize(name:str, pfp_name:str, ref_name:str) -> ArtworkCategory:
        if   name==pfp_name: return ArtworkCategory.pfp 
        elif name==ref_name: return ArtworkCategory.refsheet
        else:                return ArtworkCategory.regular

    with open(yaml_path, 'r') as file:
        yaml_artworks, artists, pfp_name, refsheet_name = load_metadata(list(yaml.safe_load_all(file)))
    artworks = []
    for source_img_path,yaml_artwork in yaml_artworks.items():
        artist_id, filename = source_img_path.split('/')
        with Image(filename=img_path/source_img_path) as source_img:
            art = Artwork(
                slug   = str(Path(filename).stem) + '-by-' + artist_id,
                artist = artists[artist_id],
                alt    = yaml_artwork['alt'],
                date   = yaml_artwork['date'],
                sha3   = yaml_artwork['sha3'],
                size   = Extent(source_img.width, source_img.height),
                thumbs = list(thumb_sizes(source_img.width, source_img.height)),
                category = categorize(source_img_path, pfp_name, refsheet_name) )
            artworks.append(art)
            if copy_images:
                copy(img_path/source_img_path, dst_path/art.slug)
            if gen_thumbs:
                generate_thumb(art.slug, art.size.w, art.size.h)
                for thumb in art.thumbs:
                    generate_thumb(art.slug, thumb.w, thumb.h)
    return artworks

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
