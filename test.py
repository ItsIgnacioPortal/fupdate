import os
import pyuac
os.system("whoami")
if not pyuac.isUserAdmin():
	print("Admin privileges are needed!")