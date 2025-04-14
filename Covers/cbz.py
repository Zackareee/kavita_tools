import zipfile
import xml.etree.ElementTree as ET
import io
import os

class CBZ:
    def __init__(self, path):
        self.path = path
        self.zip = None
        self.files = {}  # filename -> bytes
        self.xml_root = None

    def load(self):
        self.zip = zipfile.ZipFile(self.path, 'r')
        for item in self.zip.infolist():
            self.files[item.filename] = self.zip.read(item.filename)
        self._load_comicinfo()

    def _load_comicinfo(self):
        try:
            data = self.files['ComicInfo.xml']
            self.xml_root = ET.fromstring(data)
        except KeyError:
            self.xml_root = ET.Element('ComicInfo')

    def get_tag(self, tag):
        elem = self.xml_root.find(tag)
        return elem.text if elem is not None else None

    def set_tag(self, tag, value):
        elem = self.xml_root.find(tag)
        if elem is None:
            elem = ET.SubElement(self.xml_root, tag)
        elem.text = value

    def replace_file(self, name, content_bytes):
        self.files[name] = content_bytes

    def replace_file_from_path(self, name, source_path):
        with open(source_path, 'rb') as f:
            self.files[name] = f.read()




    def save(self, output_path):
        buffer = io.BytesIO()
        ET.ElementTree(self.xml_root).write(buffer, encoding='utf-8', xml_declaration=True)
        buffer.seek(0)
        self.files['ComicInfo.xml'] = buffer.read()

        with zipfile.ZipFile(output_path, 'w') as out_zip:
            for name, content in self.files.items():
                out_zip.writestr(name, content)

        if self.zip:
            self.zip.close()
