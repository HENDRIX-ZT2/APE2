from struct import unpack,pack

def getstring128(x): return datastream[x:x+128].rstrip(b"\x00").decode("utf-8")
def getint(x): return unpack('i',datastream[x:x+4])[0]

def read_linked_list(pos):
	global matnames
	blockid = getint(pos)
	typeid = getint(pos+4)
	childstart = getint(pos+8)
	nextblockstart = getint(pos+12)
	if typeid == 3:
		matname = getstring128(pos+169)
		if matname not in matnames: matnames.append(matname)
	#if we have children, the newly created empty is their parent
	if childstart!= 0:
		pos = childstart
		read_linked_list(pos)
	#for the next block, the old empty is the parent
	if nextblockstart!= 0:
		pos = nextblockstart
		read_linked_list(pos)
		
def process(filepath, codename, newname):
	f = open(filepath, 'rb')
	global datastream
	global matnames
	matnames = []
	datastream = f.read()
	f.close()
	
	blockcount = getint(80)
	pos = 88
	counter = 0
	while counter<blockcount:
		counter+= 1
		blockend = getint(pos+8)
		pos = blockend
	read_linked_list(pos)
	
	f = open(filepath, 'wb')
	for matname in matnames:
		newmatname = matname.replace(codename,newname).replace(codename.lower(),newname.lower())
		if newname:
			datastream = datastream.replace(pack('=128s', matname.encode('utf-8')), pack('=128s', newmatname.encode('utf-8')))
	f.write(datastream)
	f.close()
	return matnames
	
def get_bones(filepath):
	f = open(filepath, 'rb')
	global datastream
	global bonenames
	datastream = f.read()
	f.close()
	bonenames = []
	blockcount = getint(80)
	pos = 88
	counter = 0
	while counter<blockcount:
		blockid, typeid, blockend, name = unpack("i h i 64s", datastream[pos:pos+76])
		if typeid == 8:
			numbones, numweights = unpack("2i", datastream[pos+121:pos+129])
			pos += 129
			for x in range(0, numbones):
				boneid, parentid, bonegroup, bonename = unpack("3b 64s", datastream[pos+x*131:pos+67+x*131])
				bonenames.append(bonename.rstrip(b"\x00").decode("utf-8"))
		counter+= 1
		pos = blockend
	#read_linked_list(pos)
	return bonenames
