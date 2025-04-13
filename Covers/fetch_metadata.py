"""
Run this from the /Manga directory
This will check all subfolders for chapters.

"""
import requests
import re
import math
from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
import io

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
    if len(data) != 0:
        return data[0]

def get_chapter_from_manga(manga_id: str, chapter_number: int, desired_language=["en", "jp"]) -> dict:
    x = requests.get(f"https://api.mangadex.org/chapter?manga={manga_id}&chapter={chapter_number}")
    data: list[dict] = x.json()["data"]

    for lang in desired_language:
        for chapter in data:
            if chapter["attributes"].get("translatedLanguage") == lang:
                return chapter

    if data is not None:
        return data[0]

def get_chapter_number_from_filename(filename: str) -> str:
    pattern = re.compile(r"[Cc](?:h(?:apter)?)?[ ._]*([0-9]{1,4}(?:\.[0-9]+)?)")
    match = pattern.search(filename)
    if match:
        return match.group(1)

def list_subfolders():
    return [f.name for f in Path().iterdir() if f.is_dir()]

def list_cbz_files(subdir: str):
    folder = Path(subdir)
    if folder.is_dir():
        return [f.name for f in folder.glob('*.cbz') if f.is_file()]
    return []

def open_cbz(filename):
    return zipfile.ZipFile(filename, 'r')

def read_comicinfo(zipf):
    try:
        data = zipf.read('ComicInfo.xml')
        root = ET.fromstring(data)
        return root
    except KeyError:
        return ET.Element('ComicInfo')  # Create blank root if not present

def edit_tag(xml_root, tag, value):
    elem = xml_root.find(tag)
    if elem is None:
        elem = ET.SubElement(xml_root, tag)
    elem.text = value

def save_cbz(zipf, xml_root, output_filename):
    buffer = io.BytesIO()
    ET.ElementTree(xml_root).write(buffer, encoding='utf-8', xml_declaration=True)
    buffer.seek(0)

    # Read all other files into memory first
    files = {
        item.filename: zipf.read(item.filename)
        for item in zipf.infolist()
        if item.filename != 'ComicInfo.xml'
    }

    with zipfile.ZipFile(output_filename, 'w') as new_zip:
        for name, data in files.items():
            new_zip.writestr(name, data)
        new_zip.writestr('ComicInfo.xml', buffer.read())

for folder in list_subfolders():
    if folder[0] == "_":
        continue
    manga_id: str = get_manga_from_name(folder)["id"]
    chapter_ids = {}
    for filename in list_cbz_files(folder):
        chapter_number = get_chapter_number_from_filename(filename)
        chapter = get_chapter_from_manga(manga_id, math.floor(float(chapter_number)))
        print(filename)

        chapter_ids[filename] = chapter

    for filename, chapter in chapter_ids.items():
        attributes = chapter["attributes"]
        cbzfile = open_cbz(f"{folder}/{filename}")
        root = read_comicinfo(cbzfile)
        edit_tag(root, "chapterId", chapter["id"])
        edit_tag(root, "mangaId", manga_id)
        edit_tag(root, "Volume", attributes["volume"])
        edit_tag(root, "Number", attributes["chapter"])
        save_cbz(cbzfile, root, f"{folder}/{filename}")
        cbzfile.close()

