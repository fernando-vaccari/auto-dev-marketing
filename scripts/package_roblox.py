"""Pacote XML instalável no Studio; não inclui mapas, personagens nem credenciais."""
from pathlib import Path
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parent.parent
root=ET.Element('roblox',{'version':'4'})
folder=ET.SubElement(root,'Item',{'class':'Folder','referent':'AutoPostsCapture'})
props=ET.SubElement(folder,'Properties');ET.SubElement(props,'string',{'name':'Name'}).text='AutoPostsCapture'
for name,filename,kind in [('CameraController','CameraController.luau','ModuleScript'),('Sequences','Sequences.luau','ModuleScript'),('Client','Client.client.luau','LocalScript')]:
    item=ET.SubElement(folder,'Item',{'class':kind,'referent':name})
    properties=ET.SubElement(item,'Properties')
    ET.SubElement(properties,'string',{'name':'Name'}).text=name
    ET.SubElement(properties,'ProtectedString',{'name':'Source'}).text=(ROOT/'roblox'/filename).read_text()
ET.ElementTree(root).write(ROOT/'roblox'/'AutoPostsCapture.rbxmx',encoding='utf-8',xml_declaration=True)
print('Pacote Luau preparado em roblox/AutoPostsCapture.rbxmx; execução no Studio exige validação real.')
