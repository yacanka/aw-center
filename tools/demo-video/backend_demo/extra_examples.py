"""Build a genuine Outlook message with an attachment and an Office presentation."""
import os
import struct
import subprocess
import sys
from pathlib import Path

from extract_msg.ole_writer import OleWriter


def write_message(path, source):
    writer = OleWriter()
    def fixed(tag, value):
        return struct.pack('<IIII', int(tag,16), 6, value, 0)
    def content(name, tag, data):
        name = ([name] if name else []) + ['__substg1.0_' + tag]
        writer.addEntry(name, data)
        return fixed(tag, len(data) + (2 if tag.endswith('001F') else 0))
    def text(attachment, tag, data):
        return content(attachment, tag, data.encode('utf-16le'))
    directory = '__attach_version1.0_#00000000'
    writer.addEntry(directory, storage=True)
    writer.addEntry('__nameid_version1.0', storage=True)
    for name in ('00020102','00030102','00040102'):
        writer.addEntry(['__nameid_version1.0', '__substg1.0_'+name], b'')
    header = struct.pack('<8I', 0,0,0,1,0,1,0,0)
    fields = fixed('340D0003', 0x40000) + fixed('0E070003',0x10)
    for tag,value in [('001A001F','IPM.Note'),('0037001F','Atlas belge inceleme paketi'),('0C1A001F','Deniz Örnek'),('0C1F001F','deniz@example.invalid'),('0E04001F','Ekin Örnek'),('1000001F','Merhaba, Atlas belge yönetim planının inceleme kopyası ektedir.'),('007D001F','From: deniz@example.invalid\r\nTo: ekin@example.invalid\r\nDate: Mon, 2 Nov 2026 10:00:00 +0300\r\nSubject: Atlas belge inceleme paketi\r\n\r\n')]:
        fields += text(None,tag,value)
    timestamp = (1793602800+11644473600)*10000000
    fields += struct.pack('<IIQ',0x00390040,6,timestamp)
    writer.addEntry('__properties_version1.0', header+fields)
    props = fixed('37050003',1)+fixed('0E210003',0)
    for tag,value in [('3707001F','atlas.docx'),('3704001F','atlas.docx'),('370E001F','application/vnd.openxmlformats-officedocument.wordprocessingml.document')]:
        props += text(directory,tag,value)
    props += content(directory,'37010102',source.read_bytes())
    writer.addEntry([directory,'__properties_version1.0'],bytes(8)+props)
    writer.write(str(path))
    import extract_msg
    with extract_msg.openMsg(str(path)) as message:
        assert message.subject == 'Atlas belge inceleme paketi'
        assert message.attachments[0].data == source.read_bytes()


def write(output):
    write_message(output/'atlas.msg', output/'atlas.docx')
    subprocess.run([os.environ.get('AW_VIDEO_PPTX_PYTHON', sys.executable),str(Path(__file__).with_name('slides.py')),str(output/'atlas.pptx')], check=True)
