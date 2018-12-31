from tkinter import *
from tkinter import ttk

# http://tkinter.unpythonic.net/wiki/VerticalScrolledFrame

class VerticalScrolledFrame(Frame):
	"""A pure Tkinter scrollable frame that actually works!
	* Use the 'interior' attribute to place widgets inside the scrollable frame
	* Construct and pack/place/grid normally
	* This frame only allows vertical scrolling

	"""
	def __init__(self, parent, *args, **kw):
		Frame.__init__(self, parent, *args, **kw)			

		# create a canvas object and a vertical scrollbar for scrolling it
		vscrollbar = ttk.Scrollbar(self, orient=VERTICAL)
		vscrollbar.pack(fill=Y, side=RIGHT, expand=FALSE)
		canvas = Canvas(self, bd=0, highlightthickness=0,
						yscrollcommand=vscrollbar.set)
		canvas.pack(side=LEFT, fill=BOTH, expand=TRUE)
		vscrollbar.config(command=canvas.yview)
		self.canvas=canvas
		# reset the view
		canvas.xview_moveto(0)
		canvas.yview_moveto(0)

		# create a frame inside the canvas which will be scrolled with it
		self.interior = interior = ttk.Frame(canvas)
		interior_id = canvas.create_window(0, 0, window=interior,
										   anchor=NW)

		# track changes to the canvas and frame width and sync them,
		# also updating the scrollbar
		def _configure_interior(event):
			# update the scrollbars to match the size of the inner frame
			size = (interior.winfo_reqwidth(), interior.winfo_reqheight())
			canvas.config(scrollregion="0 0 %s %s" % size)
			if interior.winfo_reqwidth() != canvas.winfo_width():
				# update the canvas's width to fit the inner frame
				canvas.config(width=interior.winfo_reqwidth())
		interior.bind('<Configure>', _configure_interior)

		def _configure_canvas(event):
			if interior.winfo_reqwidth() != canvas.winfo_width():
				# update the inner frame's width to fill the canvas
				canvas.itemconfigure(interior_id, width=canvas.winfo_width())
		canvas.bind('<Configure>', _configure_canvas)

#https://mail.python.org/pipermail/tkinter-discuss/2012-January/003041.html

class AutocompleteCombobox(ttk.Combobox):  

	def set_completion_list(self, completion_list):
			"""Use our completion list as our drop down selection menu, arrows move through menu."""
			self._completion_list = completion_list  #sorted(completion_list, key=str.lower) # Work with a sorted list
			self._hits = []
			self._hit_index = 0
			self.position = 0
			self.bind('<KeyRelease>', self.handle_keyrelease)
			self['values'] = self._completion_list  # Setup our popup menu

	def autocomplete(self, delta=0):
			"""autocomplete the Combobox, delta may be 0/1/-1 to cycle through possible hits"""
			if delta: # need to delete selection otherwise we would fix the current position
					self.delete(self.position, END)
			else: # set position to end so selection starts where textentry ended
					self.position = len(self.get())
			# collect hits
			_hits = []
			for element in self._completion_list:
					if element.lower().startswith(self.get().lower()): # Match case insensitively
							_hits.append(element)
			# if we have a new hit list, keep this in mind
			if _hits != self._hits:
					self._hit_index = 0
					self._hits=_hits
			# only allow cycling if we are in a known hit list
			if _hits == self._hits and self._hits:
					self._hit_index = (self._hit_index + delta) % len(self._hits)
			# now finally perform the auto completion
			if self._hits:
					self.delete(0,END)
					self.insert(0,self._hits[self._hit_index])
					self.select_range(self.position,END)

	def handle_keyrelease(self, event):
			"""event handler for the keyrelease event on this widget"""
			if event.keysym == "BackSpace":
					self.delete(self.index(INSERT), END)
					self.position = self.index(END)
			if event.keysym == "Left":
					if self.position < self.index(END): # delete the selection
							self.delete(self.position, END)
					else:
							self.position = self.position-1 # delete one character
							self.delete(self.position, END)
			if event.keysym == "Right":
					self.position = self.index(END) # go to end (no selection)
			if len(event.keysym) == 1:
					self.autocomplete()
			# No need for up/down, we'll jump to the popup
			# list at the position of the autocompletion