from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
from PIL import Image
import requests
from io import BytesIO
from cbz import CBZ
import time

def list_subfolders():
    return [f.name for f in Path().iterdir() if f.is_dir()]

def list_cbz_files(subdir: str):
    folder = Path(subdir)
    if folder.is_dir():
        return [f.name for f in folder.glob('*.cbz') if f.is_file()]
    return []

def get_manga_from_name(manga_title: str) -> dict:
    x = requests.get(f'https://api.mangadex.org/manga?limit=20&title={manga_title}')
    data: list[dict] = x.json()["data"]
    for manga in data:
        attributes = manga["attributes"]

        if list(attributes["title"].values())[0].lower() == manga_title.lower():
            return manga
        else:
            for title in attributes["altTitles"]:
                if list(title.values())[0].lower() == manga_title.lower():
                    return manga

    return data[0]

def get_all_covers(manga_id: str, desired_languages=["en", "ja"]):
    image_ids = {}
    for language in desired_languages:
        offset = 0
        while True:

            x = requests.get(f"https://api.mangadex.org/cover?manga[]={manga_id}&locales[]={language}&offset={offset}&limit=100")
            data: list[dict] = x.json()["data"]
            if len(data) == 0:
                break

            for image in data:
                attributes = image["attributes"]
                volume = attributes["volume"]
                filename = attributes["fileName"]
                image_ids[volume] = filename
            if len(data) < 100:
                break  # last page
            offset += 100

    return image_ids

def get_volume_from_file(filename: str) -> str:
    cbz = CBZ(filename)
    cbz.load()
    volume = cbz.get_tag("Volume")
    return volume

def add_cover_to_cbz(cover: Image, filepath:str) -> None:
    cbz = CBZ(filepath)
    cbz.load()
    cbz.replace_file("folder.jpg", cover)
    cbz.set_tag("coverImage", "True")
    cbz.save(filepath)

def get_image_with_url(manga_id, filepath) -> str:
    response = requests.get(f"https://uploads.mangadex.org/covers/{manga_id}/{filepath}")
    img = Image.open(BytesIO(response.content)).convert("RGB")
    buf = BytesIO()
    img.save(buf, format='JPEG')
    return buf.getvalue()


for folder in list_subfolders():
    if folder[0] == "_":
        continue
    manga_id: str = get_manga_from_name(folder)["id"]
    needed_volumes = set()

    for filename in list_cbz_files(folder):
        cbz = CBZ(f"./{folder}/{filename}")
        cbz.load()
        if cbz.get_tag("coverImage") is None:
            volume = get_volume_from_file(f"./{folder}/{filename}")
            print(folder, filename, volume)

            needed_volumes.add(volume)
    print(needed_volumes)

    volume_covers = get_all_covers(manga_id)
    filtered_volume_covers = {k: v for k, v in volume_covers.items() if k in needed_volumes}
    for volume_num, cover_path in filtered_volume_covers.items():
        filtered_volume_covers[volume_num] = get_image_with_url(manga_id, cover_path)
        print(f"got image {cover_path}")
        time.sleep(1)

    for filename in list_cbz_files(folder):
        volume = get_volume_from_file(f"./{folder}/{filename}")
        cbz = CBZ(f"./{folder}/{filename}")
        cbz.load()
        if cbz.get_tag("coverImage") is None:
            print(f"loaded {filename}")
            add_cover_to_cbz(cover=filtered_volume_covers[volume], filepath=f"./{folder}/{filename}")


