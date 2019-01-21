from tkinter import BooleanVar,StringVar,IntVar,Tk,ttk,Menu,filedialog,Checkbutton,Text,messagebox
import random
import xml.etree.ElementTree as ET
import zipfile
import os
import sys
import re
import time
import requests
import webbrowser
from urllib import parse
from bs4 import BeautifulSoup

#custom file processing
import WIKI
import BFB
import BFMAT
import NIF
import ExtraUI
import sentences

try:
    approot = os.path.dirname(os.path.abspath(__file__))
except NameError:  # We are the main py2exe script, not a module
    import sys
    approot = os.path.dirname(os.path.abspath(sys.argv[0]))
os.environ['REQUESTS_CA_BUNDLE'] = os.path.join(approot, "cacert.pem")

def clean_directory(top, target=""):
	try:
		for rootdir, dirs, files in os.walk(top, topdown=False):
			for name in files:
				path = os.path.join(rootdir, name)
				if target in path: os.remove(path)
			for name in dirs:
				path = os.path.join(rootdir, name)
				if target in path: os.rmdir(path)
	except:
		messagebox.showinfo("Error","Could not clear "+top)
		
def create_dir(dir):
	"""
	Create folder if it does not exist
	"""
	if not os.path.exists( dir ):
		try:
			os.makedirs( dir )
		except OSError as exc: # Guard against race condition
			if exc.errno != errno.EEXIST:
				raise
	return dir		
				
				
class Application:
	def print_s(self, *msg):
		try:
			print(*msg)
		except:
			print("Could not print this!")
			
	def load_translations(self):
		self.translations={}
		self.languages_2_codes={}
		for file in os.listdir(self.dir_translations):
			if file.endswith(".txt"):
				try:
					code, lang = file[:-4].split("=")
					self.languages_2_codes[lang]=code
					self.translations[code]={}
					for line in self.read_encoded(os.path.join(self.dir_translations,file)).split("\r\n"):
						line = line.strip()
						if line:
							k,v = line.split("=")[0:2]
							self.translations[code][k] = v
				except:
					messagebox.showinfo("Error","Could not load translation " + os.path.basename(file))
					

	def read_encoded(self, file, encodings=("utf-8", 'iso-8859-1', "cp1252" ) ):
		"""Open a file and decode to UTF8"""
		f = open(file, 'rb')
		data = f.read()
		f.close()
		for encoding in encodings:
			try:
				return data.decode(encoding)
			except UnicodeDecodeError:
				messagebox.showinfo("Error","Illegal characters in encoding. Trying ANSI to UTF-8 conversion... Hit the original coder with a stick!")
		
	def write_utf8(self, file, data):
		"""Save UTF8 to file"""
		f = open(file, 'wb')
		f.write(data.encode('utf-8'))
		f.close()
		
	def debug_xml_file(self, file, err):
		"""de-bugs an xml styled file with duplicate attributes in a line that otherwise crashes the parser. Also fixes BFM files with two root tags"""
		lineno, column = err.position
		self.print_s(err.msg)
		
		self.update_message("Debugging " + os.path.basename(file))
		data = self.read_encoded(file)
		
		lines = data.split("\n")
		for line in lines:
			i = lines.index(line)
			#not well formed
			if i+1 == lineno:
				if err.code == 4:
					if "&" in line:
						self.print_s("Not well-formed - removing &")
						line = line.replace("&","and")
					else:
						self.print_s("Not well-formed - adding space")
						line = line[:column]+" "+line[column:]
			#double attr			
			if err.code == 8:
				deletelist=[]
				attribs=re.findall('[a-z,A-Z,_]*="',line)
				for attrib in attribs:
					if attribs.count(attrib)>1 and attrib not in deletelist:
						deletelist.append(attrib)
				for attr in deletelist:
					self.print_s("Duplicate attribute - removing")
					line=re.sub(attr+'[a-zA-Z0-9.\s-]*?" ', "", line, count=1)
			#junk after xml
			lines[i] = line.replace("</BFM>","")
		data = '\n'.join(lines)
		if file.endswith((".bfm",".BFM")): 
			self.print_s("Junk after XML - fixing")
			data +="\r\n</BFM>"
		else:
			if err.code == 9:
				self.print_s("Junk after XML - fixing")
				data=data[:-1]
		self.write_utf8(file, data)
			
		
	def parse_xml(self, filepath, debug = 10):
		"""Parse an XML, try to debug and return the tree"""
		#http://stackoverflow.com/questions/27779375/get-better-parse-error-message-from-elementtree
		try:
			return ET.parse(filepath)
		except ET.ParseError as err:
			self.debug_xml_file(filepath, err)
			#9 (junk) is not really supported
			if err.code in (4,8,9):
				if debug > 0: return self.parse_xml(filepath, debug = debug -1)
				else:
					messagebox.showinfo("Error","Could not debug "+filepath+". Must be debugged manually in a text editor!\n"+err.msg)
				
					
	def indent(self, e, level=0):
		i = "\n" + level*"	"
		if len(e):
			if not e.text or not e.text.strip(): e.text = i + "	"
			if not e.tail or not e.tail.strip(): e.tail = i
			for e in e: self.indent(e, level+1)
			if not e.tail or not e.tail.strip(): e.tail = i
		else:
			if level and (not e.tail or not e.tail.strip()): e.tail = i

	def get_binder(self, root_obj, tag, attr):
		for binder in root_obj.getiterator(tag):
			if binder.attrib['binderName']==attr:
				return binder
			
	def is_real(self, file):
		"""Test if an XML is something like a species that we need"""
		#Giant Sable antelope Items folder...
		file = file.lower()
		#dummies
		if ".xml" in file: 
			if "eggs" in file: return False
			if "items" in file: return False
			if "puzzles" in file: return False
			#because lang files also contain "entityname"
			if "strings" in file: return False
			if "entries" in file: return False
			
			#fine decisions for animals
			if "animals" in file and "_" in file: return False
			if "idae" in file: return False
			if "formes" in file: return False
			if "oidea" in file: return False
			if os.path.basename(file) in self.badlist: return False
			if "entities" in file: return True
	
	def is_z2f(self, name):
		return name.lower().endswith((".z2f",".zip"))
	
	def read_z2f_lib(self):
		"""Read all Z2F files in the ZT2 folder and store their contents in a dict so we find the latest version for updated files"""
		self.progbar.start()
		#this dict remembers all files and where an updated version was found so it can be fetched to construct the animal
		self.file_to_z2f = {}
		#lowercase for lookup
		self.lower_to_content = {}
		if not os.path.isdir(self.dir_zt2):
			messagebox.showinfo("Error","Could not find 'Zoo Tycoon 2' program folder!")
			self.dir_zt2 = filedialog.askdirectory(initialdir=self.dir_zt2, parent=self.parent, title="Locate 'Zoo Tycoon 2' program folder" )
			self.save_list(os.path.join(os.path.dirname(os.getcwd()),self.dir_config,"dirs_zt2.txt"), (self.dir_zt2, self.dir_downloads))
		if not os.path.isdir(self.dir_downloads):
			messagebox.showinfo("Error","Could not find ZT2's 'downloads' folder!")
			self.dir_downloads = filedialog.askdirectory(initialdir=self.dir_downloads, parent=self.parent, title="Locate ZT2 'downloads' folder" )
			self.save_list(os.path.join(os.path.dirname(os.getcwd()),self.dir_config,"dirs_zt2.txt"), (self.dir_zt2, self.dir_downloads))
		z2f_files = [os.path.join(self.dir_zt2, z2f_name) for z2f_name in os.listdir(self.dir_zt2) if self.is_z2f(z2f_name)]
		z2f_dls = [os.path.join(root, z2f_name) for root, dirs, files in os.walk(self.dir_downloads) for z2f_name in files if self.is_z2f(z2f_name)]
		files = z2f_files + z2f_dls
		self.z2f_to_path = {}
		
		#a dict of lists
		self.versions = {}
		
		#sort everything by filename instead of path
		for filepath in sorted(files, key=lambda file: os.path.basename(file)):
			self.update_message('Reading '+os.path.basename(filepath)[0:50])
			try:
				z2f_file = zipfile.ZipFile(filepath)
				#store for the zt2 issue finder
				self.z2f_to_path[z2f_file] = os.path.basename(filepath)
				contents = z2f_file.namelist()
				# now we store all contents in a dict and remember where they were from to be able to rebuild them later, also it only stores the latest versions
				for r_path in contents:
					l_path = os.path.normpath(r_path.lower())
					self.file_to_z2f[r_path] = z2f_file
					self.lower_to_content[l_path] = r_path
					#lookup by standardized name
					if l_path not in self.versions:
						self.versions[l_path] = []
					#append the path where this was found
					self.versions[l_path].append(os.path.basename(filepath))
			except zipfile.BadZipFile:
				messagebox.showinfo("Error",os.path.basename(filepath)[0:50]+' is a not a ZIP file! Maybe a RAR file?')
		self.progbar.stop()
		self.fill_entity_tree()
		self.fill_zoopedia()
				
	def zip_z2f(self, defaultname):
		"""Packs the temp dir into a Z2F of given name"""
		
		z2f_path = filedialog.asksaveasfilename(filetypes = [('Z2F', '.z2f')], defaultextension=".z2f", initialfile=defaultname, initialdir=self.dir_zt2, parent=self.parent, title="Save Z2F File" )
		if z2f_path:
			self.update_message("Creating Z2F file...")
			z2f = zipfile.ZipFile(z2f_path, 'w')
			for root, dirs, files in os.walk(os.getcwd()):
				for file in files:
					z2f.write(os.path.join(root, file), os.path.join(root, file).replace(os.getcwd(),""), zipfile.ZIP_DEFLATED)
			z2f.close()
			self.update_message("Created "+os.path.basename(z2f_path))

	def unzip_z2f(self, assorted_files):
		"""Unzips a list of files, case insensitive, from the Z2F files that have been opened on startup"""
		self.update_message("Unzipping Files")
		for lower in assorted_files:
			file = self.lower_to_content[os.path.normpath(lower.lower())]
			try: self.file_to_z2f[file].extract(file)
			except: self.update_message("ERROR: Could not unzip_z2f "+file)
		
	def find_file(self, filename, exts):
		"""Finds the best file from a list of extensions, also ignoring case, optionally stripping the extensions. First try to find temp versions, then get from Z2F if not found
		Always returns a normpath"""
		
		#first check locally
		norm = os.path.normpath(filename)
		self.print_s(filename)
		lowername = norm.lower()
		#strip extensions
		for ext in exts:
			lowername = lowername.replace(ext,"")
		for ext in exts:
			newlowername = lowername+ext
			#first check if it exists already exactly like that
			if os.path.isfile(norm):
				return norm
			#then walk to see if the file exists, but it does not have the right / missing dir
			for root, dirs, files in os.walk(os.getcwd()):
				rootrel = os.path.relpath(root)
				for file in files:
					jo = os.path.join(rootrel, file)
					if newlowername in jo.lower():
						return os.path.relpath(jo)
						
			#then look in the z2f
			#directly
			if newlowername in self.lower_to_content:
				self.unzip_z2f([self.lower_to_content[newlowername],])
				return os.path.normpath(self.lower_to_content[newlowername])
			#and also for wrong / missing paths
			for lowerc in self.lower_to_content:
				if newlowername in lowerc:
					self.unzip_z2f([self.lower_to_content[lowerc],])
					return os.path.normpath(self.lower_to_content[lowerc])
			
	def add_to_list(self, e, l, exts=("",)):
		try:
			f = self.find_file(e, exts)
			if f:
				#note: lower to be able to check for dupes effectively
				if f.lower() not in [item.lower() for item in l]:
					l.append(f)
		except:
			messagebox.showinfo("Warning",e+" does not exist! It might have been used in a BETA version but is likely irrelevant now.")
	
	def is_this_entity(self, entity, codename):
		if codename.lower()+"." in entity.lower() or codename.lower()+"_" in entity.lower():
			return True
		return False
		
	def gather_files(self, codename, newname = "", main_only=False, eggs_only=False, dependencies=False):
		"""Gathers files from XML files. Unzips and replaces if a new codingname is given exists, otherwise just return the files from temp"""
		self.print_s("Selected",codename, newname)
		#in rare cases, we want to use more than one replacer -> foliage -> see below
		replacer = re.compile(re.escape(codename), re.IGNORECASE)
		replacers = [replacer,]
		
		self.update_message("Gathering files...")
		ai_files = []
		bf_files = []
		bfm_files = []
		bfmat_files = []
		dds_files = []
		model_files = []
		xml_files = []
		dep_files = []
		
		#AI & XML files
		if newname:
			ai_files = [self.lower_to_content[entity] for entity in self.lower_to_content if self.is_this_entity(entity, codename) and "tasks" in entity]
			xml_files = [self.lower_to_content[entity] for entity in self.lower_to_content if self.is_this_entity(entity, codename) and ".xml" in entity]
			self.unzip_z2f(ai_files + xml_files)
		else:
			#better solution for walk in temp dir?
			for root, dirs, files in os.walk(os.getcwd()):
				for file in files:
					if self.is_this_entity(file, codename):
						if file.endswith((".tsk", ".beh", ".trk")):
							ai_files.append(os.path.relpath(os.path.join(root, file)))
						if file.endswith((".xml")):
							xml_files.append(os.path.relpath(os.path.join(root, file)))
		
		#as mentioned above, this must only occur for foliage
		if any("foliage" in file for file in xml_files):
			#only escape the first split so we don't replace biomes
			#this is dangerous for things like
			#showplatform, showplatform_mm
			#for x in codename.split("_"):
			self.update_message("Foliage name replace mode!!!")
			replacers.append(re.compile(re.escape(codename.split("_")[0]), re.IGNORECASE))
		
		if main_only:
			main_xmls = []
			for xml in xml_files:
				if self.is_real(xml) and not self.is_bad(xml):
					main_xmls.append(xml)
			#double check, maybe integrate into the normal check
			
			#pack loading calls with "" codename
			#thus if we have a codename, we usually want to load only that very one main XML so make sure we don't load shit
			if codename:
				if len(main_xmls) > 1:
					alt = [xml for xml in main_xmls if "\\"+codename.lower()+".xml" in xml]
					return alt
			return main_xmls
			
		if eggs_only:
			egg_xmls = []
			for xml in xml_files:
				if "eggs" in xml:
					egg_xmls.append(xml)
			return egg_xmls
				
		#only replace ai files here because we parse the xml files below
		if newname:
			for ai_file in ai_files:
				self.rename_replace_file(ai_file, replacers, newname)
		#parse XML files
		for xml in xml_files:
			#might not be parsable so we just skip it here
			#perhaps even remove the file?
			xml_tree = self.parse_xml(xml)
			if xml_tree:
				BFTypedBinder = xml_tree.getroot()
				for UIToggleButton in BFTypedBinder.getiterator("UIToggleButton"):
					default = UIToggleButton.find("./UIAspect/default")
					if default is not None:
						self.add_to_list(default.attrib['image'], dds_files)
				for BFNamedBinder in BFTypedBinder.getiterator("BFNamedBinder"):
					#find the bfm
					BFActorComponent = BFNamedBinder.find("./instance/BFPhysObj/BFActorComponent")
					if BFActorComponent is not None:
						if "actorfile" in BFActorComponent.attrib:
							self.add_to_list(BFActorComponent.attrib['actorfile'], bfm_files)
					#find static models
					for type in ("BFSimpleLODComponent", "BFRSceneGraphComponent", "BFSceneGraphComponent"):
						component = BFNamedBinder.find("./instance/BFPhysObj/"+type)
						if component is not None:
							self.add_to_list(component.attrib['modelfile'], model_files, (".bfb", ".nif"))
					#find skins
					BFSharedRandomTextureInfo = BFNamedBinder.find("./shared/BFSharedRandomTextureInfo")
					if BFSharedRandomTextureInfo is not None:
						for replacementSet in BFSharedRandomTextureInfo:
							for group in replacementSet:
								for item in group:
									#mat = item.attrib['material']
									self.add_to_list(item.attrib['image'], dds_files)
					if BFNamedBinder.attrib['binderName'] == 'texController':
						stateList = BFNamedBinder.find("./instance/BFAITextureController/stateList")
						for state in stateList:
							textureData = state.find("./textureData")
							for binder in textureData:
								self.add_to_list(binder.attrib['image'], dds_files)
				for ZTPuzzlePiece in BFTypedBinder.getiterator("ZTPuzzlePiece"):
					self.add_to_list(codename+"/"+ZTPuzzlePiece.attrib['texture'], dds_files)
				self.rename_replace_file(xml, replacers, newname)
		
		#xmls done, inspect BFMs now
		for bfm_file in bfm_files:
			bfm_tree = self.parse_xml(bfm_file)
			BFM = bfm_tree.getroot()
			self.add_to_list(BFM.attrib["modelname"], model_files, (".bfb", ".nif"))
			if newname:
				BFM.attrib["modelname"] = replacer.sub(newname, BFM.attrib["modelname"])
				Graph = BFM.find("./Graph")
				Graph.attrib["name"] = replacer.sub(newname, Graph.attrib["name"])
				self.indent(BFM)
				bfm_tree.write(bfm_file)
				self.rename_replace_file(bfm_file, replacers, newname)
				
			#for the dependency checker
			for animation in BFM:
				try:
					dep_files.append(animation.attrib["anim"])
				except:
					pass
		if dependencies:
			return dep_files
		
		#BFMs done, inspect models now
		for model in model_files:
			if model.endswith(".bfb"):
				for matname in BFB.process(model, codename, newname):
					self.add_to_list(matname+".bfmat", bfmat_files)
			if model.endswith(".nif"):
				for ddsname in NIF.process(model, codename, newname):
					self.add_to_list(ddsname, dds_files)
			self.rename_replace_file(model, replacers, newname)
			
		#models done, inspect BFMATs now
		for bfmat in bfmat_files:
			for texture in BFMAT.process(bfmat, codename, newname):
				self.add_to_list(texture, dds_files)
			self.rename_replace_file(bfmat, replacers, newname)
		
		#BFMATs done, rename DDSs now
		for dds in dds_files:
			self.rename_replace_file(dds, replacers, newname)
			
		return ai_files, bf_files, bfm_files, bfmat_files, dds_files, model_files, xml_files
		
	def rename_replace_file(self, file, replacers, new):
		""" Rename a file, if a new name is given. Replace its content if possible too, ie. in XML type files where length does not matter"""
		try:
			os.chmod(file, 0o664)
			if new:
				if file.endswith((".beh",".tsk",".xml",".bfmat",)):
					for replacer in replacers:
						self.write_utf8(file, replacer.sub(new, self.read_encoded(file)))
					self.pretty_print(file)
				#the first one may already change the name, so beware
				for replacer in replacers:
					try:
						os.renames(file, replacer.sub(new, file))
						file = replacer.sub(new, file)
				#self.print_s("renamed",file,replacers[0].sub(new, file))
					except:
						self.print_s("failed",file)
						pass
		except:
			#for example, happens when the same icon is called by two gift xmls
			self.update_message("File "+file+" has already been renamed and replaced.")
			
	def load_z2f(self):
		"""Unzips a Z2F file into the temp dir and loads the entities into the project"""
		start = time.clock()
		z2f_list = filedialog.askopenfilenames(filetypes = [('Z2F', '.z2f')], defaultextension=".z2f", initialdir=self.dir_zt2, parent=self.parent, title="Load Z2F File" )
		if z2f_list:
			for z2f in z2f_list:
				self.update_message("Unzipping "+os.path.basename(z2f))
				z = zipfile.ZipFile(z2f,"r")
				z.extractall("")
				z.close()
			#find new entities
			for main_xml in self.gather_files("", main_only=True):
				codename = os.path.basename(main_xml)[:-4]
				if codename not in self.project_entities:
					self.project_entities.append(codename)
			self.update_ui("")
		self.update_message("Done in {0:.2f} seconds".format(time.clock()-start))
		
	def save_and_test(self):
		"""If something is in the project, save it and run ZT.exe"""
		if self.save_z2f(): os.startfile(os.path.join(self.dir_zt2,"zt.exe"))
		
	def save_z2f(self):
		"""If something is in the project, save it"""
		if self.project_entities:
			name = "z"
			for codename in self.project_entities:
				name += "_"+codename
			if len(name) > 50:
				name = name[0:49]
			try:
				self.zip_z2f(name)
			except PermissionError:
				messagebox.showinfo("Error","You do not have the required permission to save here, or you are trying to overwrite a file that is already opened!")
		else:
			self.update_message("Nothing to save!")
		
	def find_dependencies(self):
		"""If something is in the project, see if it needs other anims"""
		z2f_dependencies = []
		missing_anims = []
		if self.project_entities:
			report = ""
			for codename in self.project_entities:
				for r_path in self.gather_files(codename, dependencies=True):
					l_path = os.path.normpath(r_path.lower())
					try:
						for z2f_name in self.versions[l_path]:
							if z2f_name not in z2f_dependencies:
								z2f_dependencies.append(z2f_name)
					except:
						missing_anims.append(os.path.basename(r_path))
				report += "\n\n"+codename+" requires animations from:\n"+"\n".join(z2f_dependencies)
				if missing_anims:
					report+="\nThe following animations are missing from your installation:\n"+"\n".join(missing_anims)
			messagebox.showinfo("Dependencies",report.strip())
		else:
			self.update_message("Load or clone something first, then try again!")
			
	def find_interferences(self):
		"""Load a z2f file and see which parts of it are overwritten by which ensuing files."""
		start = time.clock()
		z2f_list = filedialog.askopenfilenames(filetypes = [('Z2F', '.z2f')], defaultextension=".z2f", initialdir=self.dir_zt2, parent=self.parent, title="Find Interferences with this Z2F File" )
		if z2f_list:
			for z2f_path in z2f_list:
				z2f_name = os.path.basename(z2f_path)
				self.update_message("Reading "+z2f_name)
				z = zipfile.ZipFile(z2f_path,"r")
				contents = z.namelist()
				z.close()
				interferences = []
				for r_path in contents:
					l_path = os.path.normpath(r_path.lower())
					overwrites = self.versions[l_path]
					#see if it exists in other files as well
					if len(overwrites) > 1:
						ind = overwrites.index(z2f_name)
						#start at the given index of this z2f file and see what comes after
						for overwriter in overwrites[ind+1:]:
							if overwriter not in interferences:
								interferences.append(overwriter)
						#print(overwrites)
				report = "Contents of "+z2f_name+" are overwritten by:\n"+"\n".join(interferences)
				messagebox.showinfo("Interferences",report)
		self.update_message("Done in {0:.2f} seconds".format(time.clock()-start))
		
	def create_hack(self):
		"""Dynamic hack creation"""
		
		if self.abort_erase(): return
		
		self.update_message("Gathering Files")
		assorted_files = [entity for entity in self.file_to_z2f if os.path.dirname(entity) in self.entity_types and self.is_real(entity)]
		self.unzip_z2f(assorted_files)
		self.update_message("Creating Hack")
		# options_BFAIEntityDataShared = {"s_Product":"AD" }
		# options_ZTPlacementData		 = {}
		# options_footself.print_s			 = {}
		options_BFAIEntityDataShared = {"f_RequiredInitialSpace":"1",
										"f_RequiredAdditionalSpace":"1",
										"f_RequiredInitialTankSpace":"1",
										"f_RequiredAdditionalTankSpace":"1",
										"f_RequiredTankDepth":"1"}
		options_ZTPlacementData		 = {"waterPlacement":"true",
										"tankPlacement":"true",
										"landPlacement":"true"}
		options_footself.print_s			 = {"width":"1",
										"height":"1"}
		
		#results=[]
		for rootdir, dirs, files in os.walk(os.getcwd()):
			for file in files:
				if "frontgate" not in file:
					xml_path=os.path.join(rootdir, file)
					xml_tree = self.parse_xml(xml_path)
					if xml_tree is not None:
						BFTypedBinder = xml_tree.getroot()
						BFAIEntityDataShared = BFTypedBinder.find("./shared/BFAIEntityDataShared")
						if BFAIEntityDataShared is not None:
							#for item in BFAIEntityDataShared.keys():
							#	if item not in results: results.append(item)
							for option in options_BFAIEntityDataShared:
								#only overwrite
								if option in BFAIEntityDataShared.attrib: BFAIEntityDataShared.attrib[option]=options_BFAIEntityDataShared[option]
								#BFAIEntityDataShared.attrib[option]=options_BFAIEntityDataShared[option]
						ZTPlacementData = BFTypedBinder.find("./shared/ZTPlacementData")
						if ZTPlacementData is not None:
							for option in options_ZTPlacementData: ZTPlacementData.attrib[option]=options_ZTPlacementData[option]
							cfootself.print_s = ZTPlacementData.find("./cfootself.print_s")
							if cfootself.print_s is not None: 
								for option in options_footself.print_s: cfootself.print_s.attrib[option]=options_footself.print_s[option]
							dfootself.print_s = ZTPlacementData.find("./dfootself.print_s")
							if dfootself.print_s is not None: 
								for option in options_footself.print_s: dfootself.print_s.attrib[option]=options_footself.print_s[option]
						BFGBiomeData = BFTypedBinder.find("./shared/BFGBiomeData")
						if BFGBiomeData is not None:
							max = "10"
							if "locationSensitivity" in BFGBiomeData.attrib: max = BFGBiomeData.attrib["locationSensitivity"]
							for biome in BFGBiomeData: biome.attrib["sensitivity"]=max
						
						self.indent(BFTypedBinder)
						xml_tree.write(xml_path)
		#results.sort()
		#self.save_list("test.txt", results)
		
		self.zip_z2f("zBiomeSpacePlacementHack.z2f")
		
		clean_directory(os.getcwd())
		
	def find_bugs(self):
		"""Dynamic bug finder. Only reports bugs from space in location atm."""
		
		if self.abort_erase(): return
		start = time.clock()
		self.update_message("Gathering Files")
		assorted_files = [entity for entity in self.file_to_z2f if os.path.dirname(entity) in self.entity_types and self.is_real(entity)]
		self.unzip_z2f(assorted_files)
		self.update_message("Looking for Bugs")
		
		for rootdir, dirs, files in os.walk(os.getcwd()):
			for file in files:
				if "frontgate" not in file:
					xml_path=os.path.join(rootdir, file)
					xml_tree = self.parse_xml(xml_path)
					if xml_tree is not None:
						BFTypedBinder = xml_tree.getroot()
						BFGBiomeData = BFTypedBinder.find("./shared/BFGBiomeData")
						if BFGBiomeData is not None:
							loc = BFGBiomeData.attrib["location"]
							if " " in loc:
								#change this?
								realfile = self.find_file(file)
								z2f = self.file_to_z2f[realfile]
								z2fname = self.z2f_to_path[z2f]
								messagebox.showinfo("Found Bug","Space in "+loc+" location in "+file+" in "+z2fname)
		clean_directory(os.getcwd())
		self.update_message("Done in {0:.2f} seconds".format(time.clock()-start))

	def build_bfms(self):
		nodes=[]
		bffolder = filedialog.askdirectory(initialdir=os.getcwd(),mustexist=True,parent=self.parent,title="Select a folder containing BFM/NIF and BF files")
		if bffolder:
			bflist = [bf[:-3] for bf in os.listdir(bffolder) if bf.endswith(".bf")]
			niflist = [model[:-4] for model in os.listdir(bffolder) if (model.endswith(".nif") or model.endswith(".bfb"))]
			
			if niflist and bflist:
				for nif in niflist:
					name=nif.split("_")[0]
					BFM = ET.Element('BFM')
					BFM.attrib["modelname"] = "entities/units/animals/"+name+"/"+nif+".nif"
					shortnames = []
					for anim in bflist:
						split = anim.split("_")
						if split[-2] not in nodes:
							nodes.append(split[-2])
						short_anim = "_".join(anim.split("_")[-2:])
						shortnames.append(short_anim)
						animation=ET.SubElement(BFM, "animation")
						animation.attrib["anim"] = "entities/units/animals/"+name+"/"+anim+".bf"
						animation.attrib["animName"] = short_anim
						animation.attrib["animSpeed"] = "1.0"
						animation.attrib["explicitUseOnly"] = "false"
						animation.attrib["debug"] = "false"
						animation.attrib["resolveUnitCollisions"] = "true"
						animation.attrib["load"] = "true"
					Graph=ET.SubElement(BFM, "Graph")
					Graph.attrib["name"] = nif
					Graph.attrib["version"] = "1"
					for nodename in nodes:
						node = ET.SubElement(Graph, "node")
						node.attrib["name"] = nodename
						table = ET.SubElement(node, "table")
						for anim in shortnames:
							if anim.startswith(nodename+"_"):
								if nodename+"_2" in anim:
									edgename = anim.replace(nodename+"_2","")
									edge=ET.SubElement(node, "edge")
									edge.attrib["name"] = edgename
									etable=ET.SubElement(edge, "table")
									ET.SubElement(etable, anim)
								else:
									ET.SubElement(table, anim)
					
					bfmtree=ET.ElementTree()
					bfmtree._setroot(BFM)
					self.indent(BFM)
					bfm_path = bffolder+"/"+nif+".bfm"
					try:
						bfmtree.write(bfm_path)
					except:
						os.chmod(bfm_path, 0o664)
						bfmtree.write(bfm_path)
				printstr=""
				for nif in niflist:
					printstr+=nif+".bfm\n"
				messagebox.showinfo("Created BFMs", printstr)
				return
		messagebox.showinfo("Error","Select a folder containing at least one BFB or NIF model and BF animations.")
	
	def get_virtual_nodes(self, file):
		"""Dynamic bug finder. Only reports bugs from space in location atm."""
		virtual_nodes = []
		#xml_path=os.path.join(rootdir, file)
		xml_tree = self.parse_xml(file)
		if xml_tree is not None:
			BFTypedBinder = xml_tree.getroot()
			for BFNamedBinder in BFTypedBinder.getiterator("BFNamedBinder"):
				#find the bfm
				BFAIEntityDataShared = BFTypedBinder.find("./shared/BFAIEntityDataShared")
				if BFAIEntityDataShared is not None:
					for att in BFAIEntityDataShared.attrib:
						if att.startswith("p_"): virtual_nodes.append(att)
			for BFNamedBinder in BFTypedBinder.getiterator("BFNamedBinder"):
				#find the bfm
				virtualNodes = BFNamedBinder.find("./shared/BFSharedPhysVars/virtualNodes")
				if virtualNodes is not None:
					for node in virtualNodes:
						virtual_nodes.append(node.tag)
		return virtual_nodes
	
	def debug_entity(self):
		"""Debugger for everything in the current project"""
		
		codename = self.var_current_codename.get()
		if codename:
			ai_files, bf_files, bfm_files, bfmat_files, dds_files, model_files, xml_files = self.gather_files(codename)
			self.update_message("Looking for Bugs")
			
			self.behsets_e = []
			self.behsets_n = []
			self.anims_e = []
			self.anims_n = []
			#bones in lowercase
			self.bones_e = []
			self.bones_n = []
			self.macros_e = []
			
			for file in model_files:
				if file.endswith(".bfb"):
					for bone in BFB.get_bones(file):
						if bone not in self.bones_e:
							self.bones_e.append(bone)
							
			for file in xml_files:
				xml_tree = self.parse_xml(file)
				if xml_tree is not None:
					BFTypedBinder = xml_tree.getroot()
					for BFNamedBinder in BFTypedBinder.getiterator("BFNamedBinder"):
						BFAIEntityDataShared = BFTypedBinder.find("./shared/BFAIEntityDataShared")
						if BFAIEntityDataShared is not None:
							for att in BFAIEntityDataShared.attrib:
								if att.startswith("p_"):
									self.bones_e.append(att.lower())
					for BFNamedBinder in BFTypedBinder.getiterator("BFNamedBinder"):
						MACROS = BFNamedBinder.find("./shared/BFTextTagMacrosComponent/MACROS")
						if MACROS is not None:
							for macro in MACROS:
								te = macro.attrib["text"]
								s=te.split("'")
								for i in range(0,len(s)):
									if not i%2==0:
										self.macros_e.append(s[i])
								#self.print_s(re.search("'(.*)'", macro.attrib["text"]).group(1))
						virtualNodes = BFNamedBinder.find("./shared/BFSharedPhysVars/virtualNodes")
						if virtualNodes is not None:
							for node in virtualNodes:
								self.bones_e.append(node.tag.lower())

			#self.print_s(ai_files, bfm_files)
			for file in bfm_files:
				BFM = self.parse_xml(file).getroot()
				for animation in BFM.findall("animation"):
					animName = animation.attrib["animName"]
					#test only if using 1 list for all
					#would be better to test every single bfm seperately
					if animName not in self.anims_e:
						self.anims_e.append(animName)
			
			for file in ai_files:
				if file.endswith(".beh"):
					BehaviorSets = self.parse_xml(file).getroot()
					self.debug_ai(BehaviorSets)
					for behavior in BehaviorSets:
						self.behsets_e.append(behavior.tag)
			for file in ai_files:
				if file.endswith(".tsk"):
					BFAITaskTemplateList = self.parse_xml(file).getroot()
					self.debug_ai(BFAITaskTemplateList)
			
			self.anims_m = [anim for anim in self.anims_n if anim not in self.anims_e]
			self.macros_m = [anim for anim in self.macros_e if anim not in self.anims_e]
			self.bones_m = [bone for bone in self.bones_n if bone.lower() not in self.bones_e]
			self.behsets_m = [behset for behset in self.behsets_n if behset not in self.behsets_e]
			messagebox.showinfo("Debugging Info","These nodes are used in the BEH and TSK but not defined in the BFB or XML virtual nodes: "+str(self.bones_m)+"\n\nThese animations are used in the XML macros but not defined in the BFM: "+str(self.macros_m)+"\n\nThese animations are used in the BEH and TSK but not defined in the BFM: "+str(self.anims_m)+"\n\n These BEH sets are used in the BEH and TSK but not defined in the BEH: "+str(self.behsets_m))
			self.update_message("Done")
		
		
	def debug_ai(self, el):
		"""Parse along an element and log its content"""
		for child in el:
			self.debug_ai(child)
			if el.tag == "randomAnims":
				self.anims_n.append(child.tag)
		for att in el.attrib:
			if att in ("anim", "targetAnim"):
				self.anims_n.append(el.attrib[att])
			if att in ("behSet", "detachBehSet", "targetBehSet", "subjectBehSet"):
				self.behsets_n.append(el.attrib[att])
			if att in ("subjectNode", "targetNode"):
				self.bones_n.append(el.attrib[att])
			
	
	def abort_erase(self):
		if self.project_entities:
			if not messagebox.askokcancel("Warning","Continuing will erase your current project! Do you want to continue?"): return True

		#clean the gui and project files and clean temp, just to be sure
		for entity in self.project_entities: self.delete_entity()
		clean_directory(os.getcwd())
		return False
		
	def document(self):
		"""ZT2 documentation generator"""
		
		if self.abort_erase(): return
		
		self.update_message("Gathering Files")
		assorted_files = [entity for entity in self.file_to_z2f if "tasks" in entity.lower()]
		self.unzip_z2f(assorted_files)
		self.update_message("Looking for Bugs")
		self.log_children={}
		self.log_attribs={}
		self.log_parameters={}
		for rootdir, dirs, files in os.walk(os.getcwd()):
			for file in files:
				xml_path=os.path.join(rootdir, file)
				xml_tree = self.parse_xml(xml_path)
				if xml_tree is not None:
					BFTypedBinder = xml_tree.getroot()
					self.scan(BFTypedBinder)
		if True:
			#cut = 100
			children_cut = 99999
			attribs_cut = 99999
			parameters_cut = 5
			for e in self.log_children:
				if len(self.log_children[e]) > children_cut:
					self.log_children[e] = self.log_children[e][0:children_cut]#+["..."]
			for e in self.log_attribs:
				if len(self.log_attribs[e]) > attribs_cut:
					self.log_attribs[e] = self.log_attribs[e][0:attribs_cut]#+["..."]
			for e in self.log_parameters:
				if len(self.log_parameters[e]) > parameters_cut:
					self.log_parameters[e] = self.log_parameters[e][0:parameters_cut]#+["..."]
		
		clean_directory(os.getcwd())
		
		self.str=""
		self.export("behaviors")
		self.write_utf8("behaviors.txt", self.str)
		self.str=""
		self.export("BFAITaskTemplateList")
		self.write_utf8("BFAITaskTemplateList.txt", self.str)
		self.str=""
		self.update_message("Done")
	
	def export2(self, el, lv=0):
		try:
			self.str += "->"*lv + el
			try:
				for att in self.log_attribs[el]:
					self.str += " "+att+"=("+", ".join(self.log_parameters[att])+"),"
			except:
				pass
			self.str += "\n"
			for child in self.log_children[el]:
				self.export(child, lv=lv+1)
		except: pass
		
	def export(self, el, lv=0):
		#try:
		ignored_children = ("animTable", "behaviorTable","randomAnims", "randomSets", "textkeys", "avoidEntityTypes", "TrickLearning", "Subjects_AND", "Targets_AND", "emoteSets")
		self.str += "\n\n---\n\n## "+el
		self.str += "\n#### Attributes:"
		if el in self.log_attribs:
			for att in sorted(self.log_attribs[el]):
				pstring = ", ".join(sorted(self.log_parameters[att]))+"),"
				if self.log_parameters[att][0].lower() in ("true", "false"):
					ty = "bool"
				elif "." in self.log_parameters[att][0].lower():
					ty = "float"
				else:
					try:
						i = int(self.log_parameters[att][0].replace("GE","").replace("LE","").replace("E",""))
						ty = "int"
					except:
						ty = "string"
				self.str += "\n- __"+att+"__ (_"+ty+"_) - ("+pstring
		else:
			self.str += "\n- None"
		self.str += "\n#### Children:"
		if el in self.log_children and el not in ignored_children:
			for child in sorted(self.log_children[el]):
				self.str += "\n- ["+child+"](#"+child.lower()+")"
		else:
			self.str += "\n- None"
		
		#and log its children
		if el in self.log_children and el not in ignored_children:
			for child in sorted(self.log_children[el]):
				self.export(child, lv=lv+1)
		#except: pass
		
	def scan(self, el):
		"""Parse along an element and log its content"""
		for child in el:
			if el.tag not in ("Subjects", "Targets", "Objects", ):
				#why does it include the parent here
				if child.tag not in ("behaviors", "subjects", el.tag):
					if el.tag not in self.log_children:
						self.log_children[el.tag] = []
					if child.tag not in self.log_children[el.tag]:
						self.log_children[el.tag].append(child.tag)
			self.scan(child)
		for att in el.attrib:
			if el.tag not in self.log_attribs:
				self.log_attribs[el.tag] = []
			if att not in self.log_attribs[el.tag]:
				self.log_attribs[el.tag].append(att)
				
			if att not in self.log_parameters:
				self.log_parameters[att] = []
			if el.attrib[att] not in self.log_parameters[att]:
				self.log_parameters[att].append(el.attrib[att])
			
	
	def open_temp_dir(self):
		"""Opens the temp directory in Windows Explorer"""
		os.startfile(os.getcwd())

	def exit(self):
		app_root.quit()
		
	def create_menubar(self):
		#menu
		menubar = Menu(app_root)
		#Start menu
		filemenu = Menu(menubar, tearoff=0)
		menubar.add_cascade(label="Start", menu=filemenu)
		filemenu.add_command(label="Load Z2F", command=self.load_z2f)
		filemenu.add_command(label="Save Z2F", command=self.save_z2f)
		filemenu.add_command(label="Save Z2F and Test", command=self.save_and_test)
		filemenu.add_command(label="Open Temp Dir", command=self.open_temp_dir)
		filemenu.add_command(label="Exit", command=self.exit)
		#help menu
		filemenu = Menu(menubar, tearoff=0)
		menubar.add_cascade(label="Extras", menu=filemenu)
		filemenu.add_command(label="(Re)Build BFMs", command=self.build_bfms)
		filemenu.add_command(label="Create Biome+Space+Placement Hack", command=self.create_hack)
		filemenu.add_command(label="Debug Current Entity", command=self.debug_entity)
		filemenu.add_command(label="Document ZT2 API", command=self.document)
		filemenu.add_command(label="Find Bugs in ZT2", command=self.find_bugs)
		filemenu.add_command(label="Find Dependencies", command=self.find_dependencies)
		filemenu.add_command(label="Find Interferences", command=self.find_interferences)
		filemenu.add_command(label="Rebuild Entity Filter", command=self.rebuild_badlist)
		#help menu
		filemenu = Menu(menubar, tearoff=0)
		menubar.add_cascade(label="Help", menu=filemenu)
		filemenu.add_command(label="About", command=self.about)
		filemenu.add_command(label="Online Tutorial", command=self.online_tutorial)
		filemenu.add_command(label="Online Support", command=self.online_support)
		return menubar
		
	def about(self):
		messagebox.showinfo("APE2","This program allows you to copy any entity (object, animal, etc.) you can find in your ZT2 installation. You can also change properties and create zoopedias for your projects.\nProgrammed by HENDRIX of AuroraDesigns.")
		
	def online_tutorial(self):
		webbrowser.open("http://thezt2roundtable.com/topic/11479528/1", new=2)
		
	def online_support(self):
		webbrowser.open("http://thezt2roundtable.com/topic/11485920/1/", new=2)

	def update_ui(self, event):
		"""Fill the project menu with the entities in the list, and update the current entity. Also load its properties and zoopedia"""
		#has to be longer than 0 I think
		if not self.var_current_codename.get() in self.project_entities:
			if self.project_entities: self.var_current_codename.set(self.project_entities[-1])
			else: self.var_current_codename.set("")
		#what is this try for?
		try: self.project_options.set_menu(self.var_current_codename.get(), *self.project_entities)
		except:
			self.project_options.set_menu("", *self.project_entities)
		#if self.project_entities:
		self.load_properties()
		self.load_zoopedia(self.var_language.get())
		
			
		
	def load_properties(self):
		
		#Properties tab
		self.vars_BFAIEntityDataShared={}
		
		#destroy existing buttons
		try:
			self.b_properties.destroy()
			self.s_properties.destroy()
			self.f_properties.destroy()
		except: pass
		self.b_properties = ttk.LabelFrame(self.tab_properties.interior, text="Bool")
		self.s_properties = ttk.LabelFrame(self.tab_properties.interior, text="String")
		self.f_properties = ttk.LabelFrame(self.tab_properties.interior, text="Float")
		
		self.b_properties.grid(padx=5, pady=5, row=1, column=0, rowspan=2, columnspan=2, sticky='new')
		self.s_properties.grid(padx=5, pady=5, row=1, column=2, sticky='new')
		self.f_properties.grid(padx=5, pady=5, row=2, column=2, sticky='new')
		
		self.b_properties.columnconfigure(0, weight=1)
		self.b_properties.columnconfigure(1, weight=1)
		self.f_properties.columnconfigure(0, weight=1)
		self.f_properties.columnconfigure(1, weight=1)
		#node_properties = ttk.LabelFrame(tab_properties, text="Nodes")
		
		# delete properties against a memory leak - maybe?
		# or is this enough to trash the properties?
		bools=[]
		codename = self.var_current_codename.get()
		for main_xml in self.gather_files(codename, main_only=True):
			#self.print_s(main_xml)
			BFTypedBinder = self.parse_xml(main_xml).getroot()
			BFAIEntityDataShared = BFTypedBinder.find("./shared/BFAIEntityDataShared")
			try:
				self.var_biome_location.set(BFTypedBinder.find("./shared/BFGBiomeData").attrib["location"])
				self.LabelCombobox(self.s_properties, name="Location", variable=self.var_biome_location, default=self.var_biome_location.get())
			except: pass
			#create variables for every XML property
			for att in sorted(BFAIEntityDataShared.attrib):
				if att not in self.excluded_properties:
					self.vars_BFAIEntityDataShared[att]=StringVar()
					#store bools here
					if att.startswith("b_"):
						bools.append(att)
					if att.startswith("s_"):
						self.LabelCombobox(self.s_properties, name=att[2:], variable=self.vars_BFAIEntityDataShared[att], default=BFAIEntityDataShared.attrib[att])
					if att.startswith("f_"):
						self.LabelCombobox(self.f_properties, name=att[2:], variable=self.vars_BFAIEntityDataShared[att], default=BFAIEntityDataShared.attrib[att])
			#draw bools here because they are packed nicely in a grid
			row=0
			column=0
			for i in range(0,len(bools)):
				if i == int(len(bools)/2):
					column=1
					row=0
				row+=1
				att=bools[i]
				self.Checkbutton(self.b_properties, name=att[2:], variable=self.vars_BFAIEntityDataShared[att], default=BFAIEntityDataShared.attrib[att], row=row, column=column)
			self.update_message("Loaded properties from "+main_xml)
			
	def pretty_print(self, file):
		xml_tree= self.parse_xml(file)
		self.indent(xml_tree.getroot())
		xml_tree.write(file, encoding="UTF-8")
				
	def save_properties(self):
		""" Gets the current main XML, if it exists, parses it and updates the properties from self.vars_BFAIEntityDataShared"""
		codename = self.var_current_codename.get()
		for main_xml in self.gather_files(codename, eggs_only=True) + self.gather_files(codename, main_only=True):
			if os.path.isfile(main_xml):
				xml_tree= self.parse_xml(main_xml)
				BFTypedBinder = xml_tree.getroot()
				BFAIEntityDataShared = BFTypedBinder.find("./shared/BFAIEntityDataShared")
				try:
					#rewrite the biome info from a list, which is sorted with similar biomes near to the selected one
					selected_location = self.var_biome_location.get()
					selected_biome = selected_location.split("_")[0]
					shared = BFTypedBinder.find("./shared")
					shared.remove(shared.find("./BFGBiomeData"))
					BFGBiomeData = ET.SubElement(shared, "BFGBiomeData")
					BFGBiomeData.attrib["location"] = selected_location
					BFGBiomeData.attrib["locationSensitivity"] = "10"
					index_selected_biome = self.biomes.index(selected_biome)
					for i in range(0,len(self.biomes)):
						biome = ET.SubElement(BFGBiomeData, self.biomes[i])
						if i == index_selected_biome:
							biome.attrib["sensitivity"] = "10"
							biome.attrib["primary"] = "true"
						elif i == index_selected_biome+1:
							biome.attrib["sensitivity"] = "5"
						elif i == index_selected_biome-1:
							biome.attrib["sensitivity"] = "5"
						else:
							biome.attrib["sensitivity"] = "0"
				except: pass
				for property in self.vars_BFAIEntityDataShared:
					BFAIEntityDataShared.attrib[property]=self.vars_BFAIEntityDataShared[property].get()
				self.indent(BFTypedBinder)
				xml_tree.write(main_xml, encoding="UTF-8")
				self.update_message("Saved properties to "+main_xml)
				
	def add_property(self):
		"""Adds a new property to the current XML and then reloads the properties"""
		if self.project_entities:
			new = self.var_new_property.get()
			if new:
				if new[0:2] in ("s_","b_","f_"):
					codename = self.var_current_codename.get()
					for main_xml in self.gather_files(codename, main_only=True):
						xml_tree= self.parse_xml(main_xml)
						BFTypedBinder = xml_tree.getroot()
						BFAIEntityDataShared = BFTypedBinder.find("./shared/BFAIEntityDataShared")
						BFAIEntityDataShared.attrib[new]=""
						xml_tree.write(main_xml,encoding="UTF-8")
					self.var_new_property.set("")
					self.save_properties()
					self.load_properties()
					self.update_message("Added property to "+main_xml)
				else: self.update_message("Property name must start with b_, f_ or s_!")
		else: self.update_message("Add an entity to your project before adding properties!")
		
	def fill_zoopedia(self):
		#tab_zoopedia.columnconfigure(0, weight=1)
		self.tab_zoopedia.columnconfigure(1, weight=1)
		self.tab_zoopedia.columnconfigure(2, weight=2)
		self.var_gamename = StringVar()
		self.var_language = StringVar()
		#is this needed
		languages = sorted(self.languages_2_codes.keys())
		self.var_language.set(languages[0])
		
		frame_gamename = ttk.LabelFrame(self.tab_zoopedia, text="Name")
		ttk.Entry(frame_gamename, textvariable=self.var_gamename).pack()
		
		frame_taxonomy = ttk.LabelFrame(self.tab_zoopedia, text="Taxonomy")
		i=0
		self.taxonomy_vars =[]
		for level in ["Class:","Order:","Family:","Genus:","Species:","Subspecies:"]:
			self.taxonomy_vars.append(StringVar())
			ttk.Label(frame_taxonomy, text=level).grid(row=i, column=0, sticky='nsew')
			ttk.Entry(frame_taxonomy, textvariable=self.taxonomy_vars[i]).grid(row=i, column=1, sticky='nsew')
			i+=1
			
		frame_facts = ttk.LabelFrame(self.tab_zoopedia, text="Fun Facts")
		self.text_facts = Text(frame_facts, width=25, height=10, wrap="word")
		self.text_facts.pack(expand="true", fill="both")
		
		frame_longtext = ttk.LabelFrame(self.tab_zoopedia, text="Zoopedia Text")
		self.text_long = Text(frame_longtext, width=35, height=10, wrap="word")
		self.text_long.pack(expand="true", fill="both")
		
		ttk.Button(self.tab_zoopedia, text="Save Zoopedia", command=self.save_zoopedia).grid(row=1, column=0, sticky='nsew')
		ttk.Button(self.tab_zoopedia, text="Try Wikipedia", command=self.try_WIKI).grid(row=2, column=0, sticky='nsew')
		ttk.Button(self.tab_zoopedia, text="Batch translate", command=self.batch_translate).grid(row=3, column=0, sticky='nsew')
		ttk.OptionMenu(self.tab_zoopedia, self.var_language, languages[0], *languages, command=self.load_zoopedia).grid(row=0, column=0, sticky='nsew')
		frame_gamename.grid(row=4, column=0, sticky='nsew')
		frame_taxonomy.grid(row=5, column=0, sticky='nsew')
		frame_facts.grid(row=0, column=1, sticky='nsew', rowspan=6)
		frame_longtext.grid(row=0, column=2, sticky='nsew', rowspan=6)
		
		#self.load_zoopedia(self.var_language.get())

		
	def find_lang_file(self, langcode, codename):
		langpath = os.path.join("lang",langcode)
		if os.path.isdir(langpath):
			print(langpath)
			#first step - literal
			filepath = os.path.join(langpath,codename+"_strings.xml")
			if os.path.isfile(filepath): return filepath
			#second - loop
			for file in os.listdir(langpath):
				if codename in file:
					return os.path.join(langpath, file)
			#third - brute force for shared zoopedias
			for file in os.listdir(langpath):
				filepath = os.path.join(langpath, file)
				print(filepath)
				data = self.read_encoded(filepath)
				if codename in data:
					return filepath
		#failure
		return
		
	def load_zoopedia(self, current_lang):
		#basic workflow:
		#find lang code
		#find xml file
		#parse it
		#find data
		#set data
		codename = self.var_current_codename.get()
		langcode = self.languages_2_codes[current_lang]
		filepath = self.find_lang_file(langcode, codename)
		if filepath:
			ZT2Strings = self.parse_xml(filepath).getroot()
			try:
				gamename = ZT2Strings.find("./entityname/"+codename).text
			except:
				try:
					for LOC_STRING in ZT2Strings:
						if LOC_STRING.attrib["_locID"] == "entityname:"+codename:
							gamename = LOC_STRING.text
				except:
					gamename=""
					pass
			try:
				self.var_gamename.set(gamename)
				soup = BeautifulSoup(self.read_encoded(filepath), 'html.parser')
				#find the right zoopedia incase of multizoopedias			
				zoopedia = soup.find("zoopedia_"+codename.lower())
				if not zoopedia:
					zoopedia = soup.find("LOC_STRING", {"_locID" : "zoopedia_"+codename.lower()+":entry"})
					#sometime try massive monster lookup in all bundle zoopedia files in folder
					if not zoopedia: return
				
				try: self.text_long.delete('1.0', "end")
				except: pass
				try: self.text_facts.delete('1.0', "end")
				except: pass
				for var in self.taxonomy_vars: var.set("")
				
				facts = zoopedia.find("cell", {"width" : "280"})
				if facts:
					self.text_facts.insert("end", "\n\n".join([x for x in facts.text.strip().split("\n") if x]))
					
				main = zoopedia.find("cell", {"width" : "340"})
				if main:
					unlock = main.findChildren()[0].text
					main_t = "\n".join([x.strip() for x in main.text.split("\n") if x][1:])
					self.text_long.insert("end", " ".join(main_t.split(" ")).strip())
				
				taxo_cell = zoopedia.find("cell", {"width" : "284", "pady" : "10"})
				if taxo_cell:
					taxo = taxo_cell.findAll(text=True)
					taxonomy_keys=["Class","Order","Family","Genus","Species","Subspecies"]
					for i in range(0,len(taxo)):
						for j in range(0, 5):
							if self.translation(langcode,taxonomy_keys[j])+":" in taxo[i]:
								try:
									t = taxo[i].split(": ")[1]
									if not t:
										t = taxo[i+1]
								except:
									t = taxo[i+1]
								self.taxonomy_vars[j].set(t)
								
				self.update_message("Loaded zoopedia from "+filepath)
			except:
				pass
	
	def translation(self, langcode, name):
		try: return self.translations[langcode][name]
		except: return name
		
	def limit_info(self, input, num, rand = True):
		"""Helper function to randomize and limit lists"""
		#self.print_s("limit_info",len(input),num,rand)
		output = []
		#create indices
		indices = [x for x in range(1,len(input)-1)]
		if rand:
			random.shuffle(indices)
		#self.print_s(indices)
		#test if num too long
		if len(input) < num:
			num = len(input)-1
		for i in indices[0:num]:
			output.append(input[i])
		for i in sorted(indices[0:num], reverse=True):
			input.pop(i)
		#shorten long paragraphs
		if len(input) < 4:
			input = input[0:3]
		return output, input
		
	def batch_translate(self):
		#first - see which lang is in use in the project - usually English
		initial_lang = self.var_language.get()
		#then go over all entities
		for entity in self.project_entities:
			self.var_current_codename.set(entity)
			self.var_language.set(initial_lang)
			self.update_ui("")
			self.try_WIKI()
		
	def try_WIKI(self):
		current_lang = self.var_language.get().lower()[0:2]
		gamename = self.var_gamename.get()

		if gamename:
			self.update_message("Trying WIKI for "+gamename)
			
			#set the current lang
			try:
				WIKI.set_lang(self.var_language.get().lower()[0:2])
			except:
				self.update_message("Unknown language!")
			#query the title of the article in the current language
			search = WIKI.search(gamename)
			suggest = WIKI.suggest(gamename)
			if search:
				current_title = search[0]
			else:
				if suggest:
					current_title = suggest
				else:
					messagebox.showinfo("Error","Nothing was found in the current language! Check for typos or try in another language")
					return
			self.print_s("initial suggestion:",current_title)		
			#find english wiki page for taxonomy
			try:
				#parse the language we have
				url = 'https://'+current_lang+'.wikipedia.org/wiki/'+current_title
				page = requests.get(url)
				soup = BeautifulSoup(page.content, 'html.parser')
				#if not English, get and parse English
				if current_lang != "en":
					link = soup.find("a", {"lang" : "en"})
					url = link["href"]
					if url.startswith("//"):
						url="https:"+url
					page = requests.get(url)
					soup = BeautifulSoup(page.content, 'html.parser')
			except:
				if gamename != current_title:
					messagebox.showinfo("Error","The automatically suggested page "+current_title+" has no English wikipedia page! Try searching in English or with another name!")
				else:
					messagebox.showinfo("Error",current_title+" has no English version! Try searching in English or with another name!")
					
				return
			#get the taxonomy - only in latin only from english
			try:
				tables = soup.findAll('table')
				for table in tables:
					if "biota" in table["class"]: break
					if "axo" in table["class"]: break
						
				levels = ["Class:","Order:","Family:","Genus:","Species:","Subspecies:"]
				table_list = [td.text for td in table.findChildren('td')]
				success = False
				for i in range(0,len(self.taxonomy_vars)):
					for j in range(0,len(table_list)):
						if levels[i] == table_list[j]:
							value = table_list[j+1].split("\n")[0].encode("ascii", "replace").decode("ascii").replace("?","")
							self.taxonomy_vars[i].set(value)
							success = True
							break
				if not success:
					self.update_message("Can not find taxonomy for given name!")
			except:
				self.update_message("Can not find taxonomy for given name!")
				
			#go through all installed languages and create a zoopedia for each
			#try:
			for language in sorted(self.languages_2_codes.keys()):
				#set lang for APE and wiki
				self.var_language.set(language)
				lang = language.lower()[0:2]
				#a little patch for nederlands, to get the right wiki code
				if lang == "ne":
					lang = "nl"
				###oooh, careful incase polish exists - langs must be gotten from dict in that case
				if lang == "po":
					lang = "pt"
				try:
					WIKI.set_lang(lang)
				except:
					self.update_message("Unknown language!")
				#self.print_s(lang)
				
				#get the correct title for all & only foreign languages from english wiki
				if "en" != lang:
					#if we can't find the title, we can skip the language
					try:
						title = soup.find("a", {"lang" : lang})["href"].split("/")[-1]
					except:
						continue
				else:
					title = url.split("/")[-1]
				self.var_gamename.set(parse.unquote(title.replace("_"," ")))
				#self.print_s(title)
				
				#get the text
				try:
					#self.print_s("Trying to fetch", title)
					#this must turn off auto-suggestion because the title is already set in stone from the first lookup
					#and it breaks links with ( ) parentheses!! eg nl leuw_(dier)
					page = WIKI.page(title, auto_suggest=False)
					c = page.content.replace("	"," ")#.encode("ascii", "replace").decode("ascii")
					paragraphs = c.split("\n\n\n")
					good_paragraphs =[]
					for paragraph in paragraphs:
						#split into lines
						lines = paragraph.split("\n")
						for line in lines:
							#if len(line) < 10: lines.remove(line)
							if line == "": lines.remove(line)
							#if line == " ": lines.remove(line)
						if not any(x in lines[0] for x in ("ibliogra","xtern","Footnotes","Referen","Einzelnachweis","Literatur","Web","Link")):
							#the first is the heading
							if lines[1:]:
								#if that is not empty
								if lines[1]:
									good_paragraphs.append("\n".join(lines[1:]))
					#only keep max 3 paragraphs
					paras, trash = self.limit_info(good_paragraphs, 3)
					#get one fact from each
					final_facts = []
					final_paragraphs = []
					for para in paras:
						sen = sentences.split_into_sentences(para)
						#if a paragraph has not enough sentences, we have to exclude it
						#if len(sen) > 2:
						fact, text = self.limit_info(sen, 1)
						final_facts+=fact
						final_paragraphs.append(" ".join(text))
					
					try: self.text_long.delete('1.0', "end")
					except: pass
					try: self.text_facts.delete('1.0', "end")
					except: pass
					self.text_long.insert("end", "\n\n".join(final_paragraphs))
					self.text_facts.insert("end", "\n\n".join(final_facts))
					self.save_zoopedia()
				except WIKI.PageError as err:
					messagebox.showinfo("Page Error",str(err))
				except WIKI.DisambiguationError as err:
					messagebox.showinfo("Disambiguation Error",str(err))

		else:
			self.update_message("You must name your entity first!")
			
	def save_zoopedia(self):
		#basic workflow:
		#find lang code
		#get xml file path
		#get data
		#build xml tree
		#parse tree
		codename = self.var_current_codename.get()
		if codename:
			for main_xml in self.gather_files(codename, main_only=True):
				gamename = self.var_gamename.get()
				current_lang = self.var_language.get()
				langcode = self.languages_2_codes[current_lang]
				
				BFTypedBinder = self.parse_xml(main_xml).getroot()
				BFAIEntityDataShared = BFTypedBinder.find("./shared/BFAIEntityDataShared")
				
				iconpath = BFTypedBinder.find("./shared/UIToggleButton/UIAspect/default").attrib["image"]
					
				#create zoopedia_tree
				ZT2Strings = ET.Element("ZT2Strings")
				entityname = ET.SubElement(ZT2Strings, "entityname")
				#the names
				for x in ["","_stt","_lower","_ltt"]:
					strline = self.translation(langcode,"codename"+x)
					if "+" in strline:
						linea, lineb = strline.split("+")
						line = ET.SubElement(entityname, codename+x)
						line.text = linea.replace("*",gamename)
						ET.SubElement(line, "br").tail = lineb.replace("*",gamename)
					else:
						ET.SubElement(entityname, codename+x).text = strline.replace("*",gamename)
						
				zoopedia_codename = ET.SubElement(ZT2Strings, "zoopedia_"+codename.lower())
				ET.SubElement(zoopedia_codename, "entry").text = gamename
				text = ET.SubElement(zoopedia_codename, "text")
				text = ET.SubElement(text, "color", {"r":"255", "g":"255", "b":"255"})
				ET.SubElement(text, "cell", {"pady":"0","width":"1000"})
				ET.SubElement(text, "p")
				ET.SubElement(text, "cell", {"width":"260"})
				
				#the top cell
				if "animal" in main_xml:
					#incase there is no endangerment, like for placeable ambients
					try:
						s_Endangerment = BFAIEntityDataShared.attrib["s_Endangerment"]
					except:
						s_Endangerment = "LowRisk"
					try:
						rgb = {"LowRisk":{"r":"0", "g":"255", "b":"0"}, "Vulnerable":{"r":"255", "g":"255", "b":"0"}, "Endangered":{"r":"255", "g":"125", "b":"0"}, "Critical":{"r":"255", "g":"0", "b":"0"}, "Extinct":{"r":"255", "g":"255", "b":"255"}}[s_Endangerment]
					except:
						rgb = {"r":"0", "g":"0", "b":"255"}
					try:
						BFGBiomeData = BFTypedBinder.find("./shared/BFGBiomeData")
						location = BFGBiomeData.attrib["location"]
						for biometag in BFGBiomeData:
							if "primary" in biometag.attrib:
								biome = biometag.tag
								break
					except:
						location = "grassland_worldwide"
						biome = "grassland"
					cell_top = ET.SubElement(text, "cell", {"width":"640", "height":"320", "bgimg":"ui/zoopedia/topCellBg.dds"})
					cell_innertop = ET.SubElement(cell_top, "cell", {"width":"600", "padx":"20", "pady":"20"})
					
					#the icon bit - maybe configure the width to change depeding on how many icons there are
					cell_icons = ET.SubElement(cell_innertop, "cell", {"width":"284"})
					cell_icon = ET.SubElement(cell_icons, "cell", {"width":"96", "bgimg":"ui/zoopedia/littleBox-128.tga"})
					ET.SubElement(cell_icon, "img", {"src":iconpath, "sx":"0", "sy":"0", "sw":"64", "sh":"64", "height":"96", "width":"96"})
					cell_male = ET.SubElement(cell_icons, "cell", {"width":"16"})
					ET.SubElement(cell_male, "img", {"src":"ui/zoopedia/icon_male.dds", "sx":"0", "sy":"0", "sw":"64", "sh":"64", "height":"16", "width":"16"})
					cell_female = ET.SubElement(cell_icons, "cell", {"width":"16"})
					ET.SubElement(cell_female, "img", {"src":"ui/zoopedia/icon_female.dds", "sx":"0", "sy":"0", "sw":"64", "sh":"64", "height":"16", "width":"16"})
					ET.SubElement(cell_icons, "cell", {"width":"156"})	
					ET.SubElement(cell_icons, "br")
					
					cell_statusicon = ET.SubElement(cell_icons, "cell", {"width":"32", "pady":"0"})
					ET.SubElement(cell_statusicon, "img", {"src":"ui/zoopedia/"+s_Endangerment+".dds", "sx":"0", "sy":"0", "sw":"64", "sh":"64", "height":"32", "width":"32"})
					cell_statustext = ET.SubElement(cell_icons, "cell", {"width":"224", "padx":"10", "pady":"0"})
					cell_statustext.text = self.translation(langcode,"s_Endangerment")+":"
					ET.SubElement(cell_statustext, "br")
					ET.SubElement(cell_statustext, "color", rgb).text = self.translation(langcode,s_Endangerment)
					
					cell_biome = ET.SubElement(cell_innertop, "cell", {"width":"128"})
					cell_biome.text = self.translation(langcode,biome)
					ET.SubElement(cell_biome, "br")
					ET.SubElement(cell_biome, "img", {"src":"ui/icon_biomes/icon_"+biome+".dds", "sx":"0", "sy":"0", "sw":"128", "sh":"128", "height":"96", "width":"96"})
					
					cell_location = ET.SubElement(cell_innertop, "cell", {"width":"128"})
					cell_location.text = self.translation(langcode,location)
					ET.SubElement(cell_location, "br")
					ET.SubElement(cell_location, "img", {"src":"ui/icon_maplocations/"+location+".dds", "sx":"0", "sy":"0", "sw":"128", "sh":"128", "height":"96", "width":"96"})
					
					ET.SubElement(cell_innertop, "br")
					
					cell_taxonomy = ET.SubElement(cell_innertop, "cell", {"width":"284", "pady":"10"})
					
					#possibly add italics for things in ()
					taxonomy_keys=["Class","Order","Family","Genus","Species","Subspecies"]
					for i in range(0, 5):
						if i > 2:
							ET.SubElement(cell_taxonomy, "br").tail = self.translation(langcode,taxonomy_keys[i])+": "
							ET.SubElement(cell_taxonomy, "i").text = self.taxonomy_vars[i].get()
						else:
							ET.SubElement(cell_taxonomy, "br").tail = self.translation(langcode,taxonomy_keys[i])+": "+self.taxonomy_vars[i].get()
					
					cell_brush = ET.SubElement(cell_innertop, "cell", {"width":"256", "pady":"10"})
					ET.SubElement(cell_brush, "img", {"src":"ui/zoopedia/biome/"+biome+"_zoopedia_biomebrush.dds", "sx":"0", "sy":"0", "sw":"256", "sh":"85"})
					
					ET.SubElement(text, "p")
					ET.SubElement(text, "p")
					ET.SubElement(text, "cell", {"width":"260"})
					cell_facts = ET.SubElement(text, "cell", {"width":"300"})
					cell_facts_icon = ET.SubElement(cell_facts, "cell", {"width":"64"})
					ET.SubElement(cell_facts_icon, "img", {"src":"ui/zoopedia/fact-icon64.tga", "sx":"0", "sy":"0", "sw":"64", "sh":"64"})
					cell_facts_heading = ET.SubElement(cell_facts, "cell", {"width":"176"})
					ET.SubElement(cell_facts_heading, "font", {"name":"arial", "size":"12", "shadowx":"2", "shadowy":"1", "shadowa":"50"}).text = self.translation(langcode,"fact").replace("*",gamename)
					ET.SubElement(cell_facts, "p")
					cell_fact_strings = ET.SubElement(cell_facts, "cell", {"width":"280","padx":"10","bgimg":"ui/zoopedia/factBG.tga"})
					ET.SubElement(cell_fact_strings, "p")
					for fact in self.text_facts.get(1.0,"end").split("\n\n"):
						cell_fact_icon = ET.SubElement(cell_fact_strings, "cell", {"width":"32","pady":"10"})
						ET.SubElement(cell_fact_icon, "img", {"src":"ui/zoopedia/fact-bullet.tga", "sx":"0", "sy":"0", "sw":"32", "sh":"32"})
						ET.SubElement(cell_fact_strings, "cell", {"width":"202","pady":"10"}).text = fact
						ET.SubElement(cell_fact_strings, "br")
					
					cell_main = ET.SubElement(text, "cell", {"width":"340"})
				
				else:
					cell_top = ET.SubElement(text, "cell", {"width":"640", "bgimg":"ui/zoopedia/topCellBg.dds"})
					cell_icon = ET.SubElement(cell_top, "cell", {"width":"150"})
					ET.SubElement(cell_icon, "img", {"src":iconpath, "sx":"0", "sy":"0", "sw":"64", "sh":"64"})
					cell_main = ET.SubElement(cell_top, "cell", {"width":"400","pady":"15"})
					
				#the unlocked after... line
				if "animal" in main_xml:
					try:
						f_adoptRarity = BFAIEntityDataShared.attrib["f_adoptRarity"]
						fame = str(int(f_adoptRarity)/20)
					except:
						fame = "1/2"
					cell_main.text = self.translation(langcode,"unlock").replace("*",gamename).replace("+",fame)
					
				paragraphs = self.text_long.get(1.0,"end").split("\n\n")
				for para in paragraphs:
					ET.SubElement(cell_main, "p").tail = "\n\n"+para
				ET.SubElement(text, "p")
				ET.SubElement(text, "cell", {"width":"260"})
				cell_footer = ET.SubElement(text, "cell", {"width":"620"})
				cell_footer.text = "Coded with APE2"
				
				dir = os.path.join("lang",langcode)
				if not os.path.exists(dir): os.makedirs(dir)
				filepath = os.path.join(dir, codename+"_strings.xml")
				self.indent(ZT2Strings)
				zoopedia_tree=ET.ElementTree()
				zoopedia_tree._setroot(ZT2Strings)
				zoopedia_tree.write(filepath,encoding="UTF-8")
				self.update_message("Saved zoopedia to "+filepath)
		else:
			self.update_message("You must create an entity before you can create a zoopedia!")
			
	def create_zoopedia_entry(self):
		codename = self.var_current_codename.get()
		dir = os.path.join("ui","zoopedia","entries")
		if not os.path.exists(dir): os.makedirs(dir)
		filepath = os.path.join(dir, codename+"_entries.xml")
		entries = ET.Element("entries")
		BFHelpEntry = ET.SubElement(entries, "BFHelpEntry")
		BFHelpEntry.attrib["entry"] = "zoopedia_home"
		for main_xml in self.gather_files(codename, main_only=True):
			BFHelpEntry = ET.SubElement(BFHelpEntry, "BFHelpEntry")
			if "buildings" in main_xml:
				BFHelpEntry.attrib["entry"] = "zoopedia_buildings"
			if "enrichment" in main_xml:
				BFHelpEntry.attrib["entry"] = "zoopedia_animalenrichment"
				BFHelpEntry.attrib["order"] = "zoopedia_animal2"
			if "fences" in main_xml:
				BFHelpEntry.attrib["entry"] = "zoopedia_fences"
			if "foliage" in main_xml:
				BFHelpEntry.attrib["entry"] = "zoopedia_foliage"
			if "food" in main_xml:
				BFHelpEntry.attrib["entry"] = "zoopedia_food"
			if "paths" in main_xml:
				BFHelpEntry.attrib["entry"] = "zoopedia_paths"
			if "props" in main_xml:
				BFHelpEntry.attrib["entry"] = "zoopedia_showprops"
			if "rocks" in main_xml:
				BFHelpEntry.attrib["entry"] = "zoopedia_rocks"
			if "scenery" in main_xml:
				BFHelpEntry.attrib["entry"] = "zoopedia_scenery"
			if "shelters" in main_xml:
				BFHelpEntry.attrib["entry"] = "zoopedia_shelters"
			if "animals" in main_xml:
				BFHelpEntry.attrib["entry"] = "zoopedia_animals"
				BFHelpEntry.attrib["order"] = "zoopedia_animal1"
			if "staff" in main_xml:
				BFHelpEntry.attrib["entry"] = "zoopedia_staff"
			if "transportation" in main_xml:
				BFHelpEntry.attrib["entry"] = "zoopedia_transportation"
				
			BFHelpEntry = ET.SubElement(BFHelpEntry, "BFHelpEntry")
			BFHelpEntry.attrib["entry"] = "zoopedia_"+codename.lower()
		self.indent(entries)
		entry_tree=ET.ElementTree()
		entry_tree._setroot(entries)
		entry_tree.write(filepath,encoding="UTF-8")
		self.update_message("Saved entry to "+filepath)
		
	def select_entity(self):
		"""Gathers information about the selected entity and calls the unzip_z2f function"""
		if self.tree_entity.selection():
			sel = self.tree_entity.selection()[0]
			if sel.endswith(".xml"):
				codename = os.path.basename(sel)[:-4]
				newname = self.var_newname.get()
				if newname:
					if newname not in self.project_entities:
						start = time.clock()
						self.project_entities.append(newname)
						self.gather_files(codename, newname)
						self.var_newname.set("")
						self.var_current_codename.set(newname)
						self.create_zoopedia_entry()
						self.update_ui("")
						self.update_message("Done in {0:.2f} seconds".format(time.clock()-start))
					else: self.update_message("Codename "+newname+" is already in use!")
				else: self.update_message("You must enter a codename before cloning!")
			else: self.update_message("You mustn't select a category!")
		else: self.update_message("You must select a base entity before cloning!")
		
	def delete_entity(self):
		"""Deletes files related to the current entity"""
		#use gathering instead? cleaner but risky!
		if self.project_entities:
			codename = self.var_current_codename.get()
			self.print_s("Deleting",codename)
			if codename in self.project_entities:
				self.project_entities.remove(codename)
				self.update_ui("")
				self.update_message("Deleting "+codename)
				clean_directory(os.getcwd(), codename)
		
	def fill_entity_tree(self):
		self.progbar.start()
		start = time.clock()
		self.update_message("Refilling the Entity Tree")
		self.tree_entity.delete(*self.tree_entity.get_children())
		#list comprehension to get the entities from all the content
		loaded_entities = [entity for entity in self.file_to_z2f if os.path.dirname(entity) in self.entity_types and self.is_real(entity)]
		loaded_entities.sort()
		#fill the tree_entity; the root categories are added manually
		self.tree_entity.insert('', 'end', "entities/objects/ai", text="objects")
		self.tree_entity.insert('', 'end', "entities/units/ai", text="units")
		self.tree_entity.insert('', 'end', "entities/transportation/ai", text="transportation")
		for type in self.entity_types:
			self.tree_entity.insert(os.path.dirname(os.path.dirname(type))+"/ai", 'end', type, text=os.path.basename(os.path.dirname(type)))
		for entity in loaded_entities:
			name = os.path.basename(entity)[:-4]
			#lookup is ugly
			if name: self.tree_entity.insert(os.path.dirname(entity), 'end', entity, text=name, values=(self.z2f_to_path[self.file_to_z2f[entity]]))
		self.progbar.stop()
		self.update_message("Done in {0:.2f} seconds".format(time.clock()-start))
			
	def is_bad(self, file):
		"""Checks whether a file is a named entity - good or not - bad"""
		try:
			if ".xml" in file:
				if "entityname" in self.read_encoded(file): return False
		except:
			self.update_message("Couldn't read "+file)
			return True
		return True
			
	def load_list(self, file):
		f = open(file, 'r')
		new_list = f.read().split("\n")
		f.close()
		return new_list

	def save_list(self, file, src_list):
		f = open(file, 'w')
		f.write('\n'.join(src_list))
		f.close()
						
	def rebuild_badlist(self):
		"""Builds a badlist of entities to be excluded by unzipping all XMLs that would be unzipped otherwise and checking whether they are bad"""

		if self.abort_erase(): return
		start = time.clock()
		self.update_message("Gathering Files")
		assorted_files = [entity for entity in self.file_to_z2f if os.path.dirname(entity) in self.entity_types and self.is_real(entity)]
		self.unzip_z2f(assorted_files)
		self.update_message("Building Badlist")
		for rootdir, dirs, files in os.walk(os.getcwd()):
			self.badlist+=[file.lower() for file in files if self.is_bad(os.path.join(rootdir, file))]
		clean_directory(os.getcwd())
		self.save_list(os.path.join(os.path.dirname(os.getcwd()),self.dir_config,"badlist.txt"), self.badlist)
		self.fill_entity_tree()
		self.update_message("Done in {0:.2f} seconds".format(time.clock()-start))
				
	def update_message(self, msg):
		self.print_s(msg)
		self.var_message.set(msg)
		self.label_progress.update()
				
	def __init__(self, parent):
		#basic UI setup
		self.parent = parent
		self.parent.config(menu = self.create_menubar())
		self.parent.wm_iconbitmap('APE2.ico')
		self.parent.geometry('640x480+100+100')
		top=self.parent.winfo_toplevel()
		top.rowconfigure(1, weight=3)
		top.columnconfigure(1, weight=1)
		self.parent.option_add("*Font", "Calibri 9")
		self.parent.title("ZT2 APE")
		
		#define values
		self.project_entities = []
		self.dir_config = "config"
		self.dir_defaults = "defaults"
		self.dir_translations = "translations"
		self.dir_zt2, self.dir_downloads = self.load_list(os.path.join(self.dir_config,"dirs_zt2.txt"))[0:2]
		self.biomes = self.load_list(os.path.join(self.dir_config,"biomes.txt"))
		
		self.badlist = self.load_list(os.path.join(self.dir_config,"badlist.txt"))
		self.entity_types = self.load_list(os.path.join(self.dir_config,"entity_types.txt"))
		self.excluded_properties = self.load_list(os.path.join(self.dir_config,"excluded_properties.txt"))
		self.load_translations()
		self.dict_defaults = {}
		self.var_biome_location = StringVar()
		self.var_new_property = StringVar()
		for file in os.listdir(self.dir_defaults):
			self.dict_defaults[file[:-4]]=self.load_list(os.path.join(self.dir_defaults,file))
		
		self.tabs = ttk.Notebook(self.parent)
		self.tab_clone = ttk.Frame(self.tabs)
		self.tab_clone.rowconfigure(0, weight=1)
		self.tab_clone.columnconfigure(0, weight=1)
		self.tab_properties = ExtraUI.VerticalScrolledFrame(self.tabs)
		ttk.Button(self.tab_properties.interior, text="Add Property", command=self.add_property).grid(row=0, column=0)
		
		c = ExtraUI.AutocompleteCombobox(self.tab_properties.interior, textvariable = self.var_new_property)
		c.set_completion_list(self.dict_defaults["AddProperty"])
		c.grid(sticky='ew', column=1, row=0)
		ttk.Button(self.tab_properties.interior, text="Save Changes", command=self.save_properties).grid(row=0, column=2)
		
		self.tab_zoopedia = ttk.Frame(self.tabs)
		self.tabs.add(self.tab_clone, text='Clone')
		self.tabs.add(self.tab_properties, text='Properties')
		self.tabs.add(self.tab_zoopedia, text='Zoopedia')
		
		#project manager
		ttk.Label(self.parent, text="Select current entitiy:").grid(row=0, column=0, sticky='nsew')
		self.var_current_codename = StringVar()
		self.project_options = ttk.OptionMenu(self.parent, self.var_current_codename, "", command = self.update_ui)
		self.project_options.grid(row=0, column=1, sticky='nsew')
		ttk.Button(self.parent, text="Delete from Project!", command=self.delete_entity).grid(row=0, column=2, sticky='nsew')
		
		#progress bar
		self.var_message = StringVar()
		self.label_progress = ttk.Label(self.parent, textvariable=self.var_message)
		self.update_message("Starting")
		self.progbar = ttk.Progressbar(self.parent, orient='horizontal', mode='determinate')
		self.label_progress.grid(row=2, column=0, sticky='ew', columnspan=3)
		self.progbar.grid(row=3, column=0, sticky='ew', columnspan=3)
		
		#Clone Tab
		self.tree_entity = ttk.Treeview(self.tab_clone, selectmode="browse", columns=('origin',))
		#tree = ttk.Treeview(root, columns=('size', 'modified'))
		self.tree_entity['columns'] = ('origin')
		tree_entity_scroll = ttk.Scrollbar(self.tab_clone, orient='vertical', command=self.tree_entity.yview)
		self.tree_entity.configure(yscroll=tree_entity_scroll.set)
		self.tree_entity.heading('#0', text='Select Base Entity to Clone', anchor='w')
		self.tree_entity.heading('origin', text='Origin', anchor='w')
		
		self.var_newname = StringVar()
		ttk.Entry(self.tab_clone, textvariable=self.var_newname).grid(row=1, column=0, sticky='ew')
		ttk.Button(self.tab_clone, text="Clone into Project!", command=self.select_entity).grid(row=1, column=1, sticky='ew')
		self.tree_entity.grid(row=0, column=0, sticky='nsew', columnspan=2)
		tree_entity_scroll.grid(row=0, column=2, sticky='ns')
		
		#grid the main frame
		self.tabs.grid(row=1, column=0, sticky='nsew', columnspan=3)
		
		os.chdir(create_dir( os.path.join(os.path.realpath(approot),"temp") )  )
		clean_directory(os.getcwd())
		self.parent.after(100,self.read_z2f_lib)
		
	def LabelCombobox(self, parent, name="", variable=None, default=""):
		try:
			defaults = self.dict_defaults[name]
			if default not in defaults: defaults.append(default)
		except:
			defaults=[default]
		l = ttk.Label(parent, text = name)
		c = ttk.Combobox(parent, values = defaults, textvariable = variable)
		variable.set(default)
		l.grid(sticky='new', column=0)
		c.grid(sticky='new', column=1, row=l.grid_info()["row"])
		
	def Checkbutton(self, parent, name="", variable=None, default="", row=None, column=None):
		c = ttk.Checkbutton(parent, text=name, onvalue="true", offvalue="false", variable=variable)
		variable.set(default)
		if row: c.grid(sticky='nw', column=column, row=row)
		else: c.grid(sticky='nw')
	
if __name__ == '__main__':
	app_root = Tk()
	app = Application(app_root)
	app_root.mainloop()
	clean_directory(os.getcwd())