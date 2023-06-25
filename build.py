#!/usr/bin/env python3
import yaml
from pathlib import Path
from shutil import copy,rmtree
from wand.image import Image
from math import floor
import subprocess
from fontTools import subset
from dataclasses import dataclass
from enum import Enum, verify, UNIQUE, CONTINUOUS
from typing import Iterator,Tuple

def main(skip_images = False,
         src_path    = Path(__file__).parent/"src",
         dst_path    = Path(__file__).parent/"www",
         img_path    = Path(__file__).parent/"img",
         data_path   = Path(__file__).parent/"data"):

    if not skip_images: rmtree(dst_path, ignore_errors=True)
    dst_path.mkdir(parents=True, exist_ok=True)

    if not skip_images: copy(data_path/"favicon32.png", dst_path)

    subset_font(str(data_path/"Nunito.ttf"), str(dst_path/"nunito.woff2"))

    artworks = [ load_image(meta, None if skip_images else dst_path)
                 for meta in parse_metadata(src_path/'metadata.yaml', img_path) ]

    html = gen_html(artworks, src_path)
    (dst_path/'index.html').write_text(html, encoding="utf-8")
    print("done!")

### parsing metadata ###########################################################

@dataclass(slots=True)
class Artist:
    name  : str
    links : dict[str,str]

@verify(UNIQUE, CONTINUOUS)
class ArtworkCategory(Enum):
    regular  = 0
    refsheet = 1
    pfp      = 2

    def match(self, regular, refsheet, pfp):
        match self:
            case ArtworkCategory.regular:  return regular
            case ArtworkCategory.refsheet: return refsheet
            case ArtworkCategory.pfp:      return pfp

@dataclass(slots=True)
class ArtworkMeta:
    path     : Path
    artist   : Artist
    slug     : str
    date     : str
    alt      : str
    sha3     : str
    category : ArtworkCategory

def parse_artist(id:str, artist:dict, config:dict) -> Tuple[str,Artist]:
    templates = config['link_templates']
    links = {}
    for k,v in artist['links'].items():
        url = ''
        template = templates[k].split('$')
        values   = v.split(' ') + ['']
        for a,b in zip(template,values):
            url += a
            url += b
        links[k] = url
    return id,Artist(
        name  = artist['name'],
        links = links)

def parse_artwork(artwork_path:Path, artwork:dict, artists:dict[str,Artist], config:dict) -> ArtworkMeta:
    category = ArtworkCategory.regular
    if   artwork_path==artwork_path.parents[1]/config['pfp']:
        category = ArtworkCategory.pfp
    elif artwork_path==artwork_path.parents[1]/config['refsheet']:
        category = ArtworkCategory.refsheet
    artist_id = artwork_path.parts[-2]
    filename  = artwork_path.stem
    return ArtworkMeta(
        path   = artwork_path,
        slug   = filename + '-by-' + artist_id,
        artist = artists[artist_id],
        alt    = artwork['alt'],
        date   = artwork['date'],
        sha3   = artwork['sha3'],
        category = category)

def parse_metadata(yaml_file:Path, img_path:Path) -> list[ArtworkMeta]:
    with open(yaml_file, 'r') as file:
        yaml_artworks, yaml_artists, config = list(yaml.safe_load_all(file))
    artists  = dict(map(
        lambda kv: parse_artist(kv[0], kv[1], config),
        yaml_artists.items()))
    artworks = list(map(
        lambda kv: parse_artwork(img_path/kv[0], kv[1], artists, config),
        yaml_artworks.items()))
    return artworks

### image handling #############################################################

@dataclass(slots=True)
class Extent:
    w: int
    h: int

@dataclass(slots=True)
class Artwork:
    meta   : ArtworkMeta
    size   : Extent
    thumbs : list[Extent]

def thumb_sizes(src:Extent) -> list[Extent]:
    ret = [Extent(src.w, src.h)]
    for w_exp in range(100):
        w = int(round(200*2**(floor(w_exp/2))*(1+0.5*(w_exp%2))))
        if w>=src.w: break;
        h = int(round( (w/src.w) * src.h ))
        ret.append(Extent(w,h))
    return ret;

def generate_thumbnail(img:Image, size:Extent, path:Path, slug:str, file_extension:str, quality:int) -> None:
    print(f"{slug} {file_extension} {size.w}x{size.h}")
    with img.clone() as o:
        o.thumbnail(width=size.w, height=size.h)
        o.compression_quality=quality
        o.save(filename=path/(slug + f'-{size.w}w.{file_extension}'))

def load_image(meta:ArtworkMeta, write_path:Path|None) -> Artwork:
    with Image(filename=meta.path) as img:
        src_size = Extent(img.width, img.height)
        art = Artwork(
            meta = meta,
            size   = src_size,
            thumbs = list(thumb_sizes(src_size)) )
        if write_path is not None:
            copy(art.meta.path, write_path/art.meta.slug)
            for thumb_size in art.thumbs:
                generate_thumbnail(img, thumb_size, write_path, art.meta.slug, 'avif', quality=64)
                generate_thumbnail(img, thumb_size, write_path, art.meta.slug, 'jpg',  quality=80)
    return art

### html generation ############################################################

def gen_html(artworks:list[Artwork], src_path:Path) -> str:
    gallery_html = []
    refsheet_html = ""
    pfp_html = ""
    for artwork in artworks:
        match artwork.meta.category:
            case ArtworkCategory.pfp:
                pfp_html = gen_html_pfp(artwork)
                gallery_html.append(gen_html_figure(artwork))
            case ArtworkCategory.refsheet:
                refsheet_html = gen_html_figure(artwork)
            case ArtworkCategory.regular:
                gallery_html.append(gen_html_figure(artwork))

    with open(src_path/'constants.yaml', 'r') as file:
        constants = list(yaml.safe_load_all(file))
        css_constants = constants[0]['css']

    def read_txt(filename:str):
        return (src_path/filename).read_text(encoding="utf-8")

    css = preprocess_css(read_txt("style.css"), css_constants)

    return resolve(strip_lines(read_txt("index.html")), 
                   title="Snipsel's Cozy Corner of the Internet",
                   style=css,
                   svg=strip_lines(read_txt("icons.svg")),
                   pfp=strip_lines(pfp_html),
                   refsheet=strip_lines(refsheet_html),
                   gallery=strip_lines(''.join(gallery_html)),
                   githash=git_short_hash() )

import re

def preprocess_css(css_source:str, css_constants:dict[str,str]) -> str:
    # substitute constants for var(--variable-name)
    ret = re.sub('var\(\s*--([A-Za-z0-9-]+)\s*\)',
                 lambda m: css_constants[m.group(1)],
                 css_source)

    # strip comments
    ret = re.sub('/\*(?:.*?)\*/', '', ret)

    # remove whitespace
    ret = strip_lines(ret)

    # remove spaces after : and ,
    ret = re.sub(':\s+', ':', ret)
    ret = re.sub(',\s+', ',', ret)

    # remove last ; in list
    ret = re.sub(';\s*}', '}', ret)

    print(ret)
    return ret

def resolve(template:str, **replacements: dict[str,str]):
    for tag,repl in replacements.items():
        template = template.replace('{'+tag+'}', repl);
    return template

def strip_lines(s:str):
    return ''.join(map(lambda x: x.strip(), s.splitlines()))

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

def gen_artist_links(artist:Artist) -> str:
    html = ""
    for kind,link in artist.links.items():
        html += f"""
            <a href="{link}">
                <svg>
                    <use href="#icon-{kind}"/>
                </svg>
            </a>"""
    return html

def gen_html_picture(art:Artwork):
    sizes = art.meta.category.match(
        pfp      = 'min(100vw,320px - 2rem)',
        refsheet = 'min(100vw,800px - 2rem)',
        regular  = 'min(100vw,50vh)')
    mini_jpg  = ','.join([f'{art.meta.slug}-{e.w}w.jpg {e.w}w' for e in art.thumbs])
    mini_avif = ','.join([f'{art.meta.slug}-{e.w}w.avif {e.w}w' for e in art.thumbs])

    return f"""
        <picture>
          <source type="image/avif" sizes="{sizes}" srcset="{mini_avif}">
          <source type="image/jpeg" sizes="{sizes}" srcset="{mini_jpg}">
          <img width="{art.size.w}" height="{art.size.h}" src="{art.meta.slug}-400w.jpg" alt="{art.meta.alt}">
        </picture>"""

def gen_html_figure(art:Artwork) -> str:
    yyyy,mm,dd = art.meta.date.split(' ')[0].split('-')
    month = [None, "Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][int(mm)]
    return f"""
        <figure id="{art.meta.slug}" class="artwork">
          <a href="{art.meta.slug}">
            {gen_html_picture(art)}
          </a>
          <figcaption>
            {art.meta.artist.name}
            {gen_artist_links(art.meta.artist)}
            <time datetime="{art.meta.date}">{month} {yyyy}</time>
          </figcaption>
        </figure>"""

def gen_html_pfp(art:Artwork) -> str:
    return f"""
        <figure id="pfp" class="artwork">
          {gen_html_picture(art)}
        </figure>"""

### argument parsing (TODO) ####################################################
from sys import argv

if __name__ == "__main__":
    argset = set(argv[1:])
    main(skip_images=('--skip-images' in argset))

