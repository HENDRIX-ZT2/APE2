from distutils.core import setup
import py2exe, sys, os

sys.argv.append('py2exe')

setup(data_files = [('', ['C:/Python34/Lib/site-packages/requests/cacert.pem'])],
	options={'py2exe': {"packages":[],
						"bundle_files":2,
						"excludes":[],
						"includes":["random","wikipedia",],
						"dll_excludes":['msvcr71.dll'],
						"compressed":True}},
    windows = [{'script': "APE2.py",
				"icon_resources": [(1, "APE2.ico")]
			  }],
    zipfile = "library.zip",
)

#os.startfile("C:/Python34/dist")