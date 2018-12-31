import xml.etree.ElementTree as ET

def process(filepath, codename, newname):
	textures =[]
	try:
		material = ET.parse(filepath).getroot()
	except:
		print("ERROR! Material cannot be parsed! There is likely an XML syntax error in the BFMAT file!")
		return
	for param in material:
		name = param.attrib["name"]
		text = param.text
		if name in ("Texture0", "Texture1", "Texture2"): textures.append(text+".dds")
	return textures