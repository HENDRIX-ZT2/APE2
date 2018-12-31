from struct import unpack,pack
import re
import os
def getint(x): return unpack('i',datastream[x:x+4])[0]

def find_all(a_str, sub):
    start = 0
    while True:
        start = a_str.find(sub, start)
        if start == -1: return
        yield start
        start += len(sub)

def process(filepath, codename, newname):
	global datastream
	f = open(filepath, 'rb')
	matnames = []
	datastream = f.read()
	f.close()
	#r= re.compile("[x\00]*?[^x\00]*?"+codename+"[^x\00]*?\.dds", re.IGNORECASE)
	#matches = r.findall(datastream)
	#print matches
	dds_files = []
	replacer = re.compile(re.escape(codename), re.IGNORECASE)
	old_to_new = {}
	for type in (b".dds",b".tga"):
		occurences = find_all(datastream, type)
		for x in occurences:
			dds= datastream[x:x+4]
			i=0
			while "\x00" not in dds.decode("utf-8"):
				i+=1
				dds=datastream[x-i:x+1-i]+dds
			dds=dds[1:]
			start = x-i-3
			size = getint(start)+4
			cleandds=os.path.basename(os.path.normpath(dds.decode("utf-8")))
			dds_files.append(cleandds)
			newdds = replacer.sub(newname, cleandds).encode("utf-8")
			newstr = pack('=i'+str(len(newdds))+"s", len(newdds), newdds)
			old_to_new[datastream[start:start+size]] = newstr
	if newname:
		for old in old_to_new:
			datastream = datastream.replace(old, old_to_new[old])
	f = open(filepath, 'wb')
	f.write(datastream)
	f.close()
	return dds_files