import os
import re
import semver
import requests
import json
from termcolor import colored
import urllib.parse
import subprocess
import sys

#https://gist.github.com/sylvainpelissier/ff072a6759082590a4fe8f7e070a4952
import pyuac

"""
1. Get list of all outdated packages
2. If a package has upgraded a major version number, show changelog
3. "Do you want to updated X packages? [Y/n]: "
4. Update everything
"""

devMode = True
versionNotificationSettings={
	"Major Versions": True,
	"Minor Versions": False,
	"Patch Versions": False
	}
generalUpgradeSettings={
	"gup": True,
	"pip": True,
	"pipVenvs": True,
	"git": True,
	"choco": True
	# "npm": True
}

# npm support is disabled until they fix `npm outdated -g`
# https://github.com/npm/cli/issues/6098

numberOfMajorUpgrades = 0
numberOfMinorUpgrades = 0
numberOfPatchUpgrades = 0

def error(message):
	print(colored("ERROR: ", "red") + message)

def warning(message):
	print(colored("WARNING: ", "yellow") + message)

if not pyuac.isUserAdmin():
	error("Admin privileges are needed!")
	exit()

# Setup githubtoken
try:
	githubToken = os.environ["fupdate-github-token"]
except KeyError:
	warning("No github token detected. Please set the environment variable " + colored("fupdate-github-token") + " to your github personal access token. Without it, we can't fetch the changelogs.")
	githubToken = ""


def stripLeadingV(version):
	"""Receives a function like \"v1.0.0\" and removes the trailing v\n
	EXAMPLE: \"v1.0.0\" -> \"1.0.0\""""
	if version.startswith("v"):
		return version[1:]
	else:
		return version

def forceSemver(version):
	"""Recieves a string that should ressemble a semver. This function would convert \"v3.5\" -> \"3.5.0\""""
	try:
		version = semver.VersionInfo.parse(version)
		return [version, False]
	except ValueError:
		versionSplit = version.split(".")
		for number in versionSplit:
			try:
				int(number)
			except ValueError:
				error("Unable to parse " + colored(version, "yellow") + " as a Semantic Version (See: https://semver.org)")
				return [None, Exception]
		
		if len(versionSplit) == 2:
			version = version + ".0"
			version = semver.VersionInfo.parse(version)
		else:
			return [None, Exception]
	
	return [version, True]

			

def parseVersions(newVersion: str, oldVersion: str, package: str, manager: str) -> list[bool, bool]:
	"""Recieves the raw version strings, parses them, outputs a fancy message depending on the notificationSettings\n
	First bool:  if the newVersion is newer than oldVersion\n
	Second bool: if newVersion is newer than oldVersion, but depending on the notificationSettings"""

	global numberOfMajorUpgrades
	global numberOfMinorUpgrades
	global numberOfPatchUpgrades

	newVersion = stripLeadingV(newVersion)
	oldVersion = stripLeadingV(oldVersion)

	# Parse versions that don't comply with semantic versioning
	semverNewVersion = forceSemver(newVersion)
	semverOldVersion = forceSemver(oldVersion)

	if semverNewVersion[1] == Exception or semverOldVersion[1] == Exception:
		return [False, False]
	
	semverNewVersion = semverNewVersion[0]
	semverOldVersion = semverOldVersion[0]

	if(semverNewVersion > semverOldVersion):
		if(semverNewVersion.major > semverOldVersion.major):
			print(colored("NEW MAJOR VERSION: ", "green") + colored("(" + manager + ") ", "yellow") + package + " (" + oldVersion + " to " + newVersion + ")")
			numberOfMajorUpgrades += 1
			return [True, versionNotificationSettings["Major Versions"]]

		elif(semverNewVersion.minor > semverOldVersion.minor):
			print(colored("New minor version: ", "blue") + colored("(" + manager + ") ", "yellow") + package + " (" + oldVersion + " to " + newVersion + ")")
			numberOfMinorUpgrades += 1
			return [True, versionNotificationSettings["Minor Versions"]]

		else:
			print("New patch version: " + colored("(" + manager + ") ", "yellow") + package + " (" + oldVersion + " to " + newVersion + ")")
			numberOfPatchUpgrades += 1
			return [True, versionNotificationSettings["Patch Versions"]]

	elif devMode:
		print(package + " " + oldVersion + "==" + newVersion)

	return [False,False]

def getLatestGithubRelease(repoURL: urllib.parse.ParseResult | str) -> str:

	if not isinstance(repoURL, urllib.parse.ParseResult):
		try:
			repoURL = urllib.parse.urlparse(repoURL)
		except:
			return colored("\tFATAL ERROR: ", "red") + "The github source code URL " + colored(repoURL, "yellow") + " was malformed."


	if githubToken != "":
		pathList = (repoURL.path[1:]).split("/") 
		pathListLen = len(pathList)

		#Normally pathListLen would always be equal to 2, but in the rare case where someone put the URL as (for example) "https://github.com/username/repo/", the len will be three, because of that extra slash at the end. This is also done to prevent potential CSRF or token leaks
		if pathListLen == 2 or (pathListLen == 3 and pathList[2] == "json") or (pathListLen == 4 and pathList[3] == "latest"):
			#/repos/{owner}/{repo}/releases/latest
			url = "https://api.github.com/repos/" + pathList[0] + "/" + pathList[1] + "/releases/latest"


		else:
			return colored("\tFATAL ERROR: ", "red") + "The github source code URL " + colored(repoURL, "yellow") + " was malformed."


	headers = {"Accept": "application/vnd.github+json", "Authorization": "Bearer " + githubToken, "X-GitHub-Api-Version": "2022-11-28"}
			
	#TODO: Error handling and throttling
	response = requests.get(url, headers=headers)

	responseJSON = json.loads(response.text)

	try:
		return (responseJSON["tag_name"])
	except:
		return colored("ERROR: ", "red") + "This version does not exist: " + colored(url,"yellow")


def getGithubChangelog(repoURL: urllib.parse.ParseResult | str, version):
	
	if githubToken != "":
		version = stripLeadingV(version)

		if not isinstance(repoURL, urllib.parse.ParseResult):
			try:
				repoURL = urllib.parse.urlparse(repoURL)
			except:
				return colored("\tFATAL ERROR: ", "red") + "The github source code URL " + colored(repoURL, "yellow") + " was malformed."


		pathList = (repoURL.path[1:]).split("/") 
		pathListLen = len(pathList)

		#Normally pathListLen would always be equal to 2, but in the rare case where someone put the URL as (for example) "https://github.com/username/repo/", the len will be three, because of that extra slash at the end. This is also done to prevent potential CSRF or token leaks
		if pathListLen == 2 or (pathListLen == 3 and pathList[2] == "json") or (pathListLen == 4 and pathList[3] == "latest"):
			
			latestVersion = getLatestGithubRelease(repoURL)
			if latestVersion.startswith("v"):
				version = "v" + version

			url = "https://api.github.com/repos/" + pathList[0] + "/" + pathList[1] + "/releases/tags/" + version

		else:
			return colored("\tFATAL ERROR: ", "red") + "The github source code URL " + colored(repoURL, "yellow") + " was malformed."


		headers = {"Accept": "application/vnd.github+json", "Authorization": "Bearer " + githubToken, "X-GitHub-Api-Version": "2022-11-28"}
		
		#TODO: Error handling and throttling
		response = requests.get(url, headers=headers)

		responseJSON = json.loads(response.text)

		try:
			return responseJSON["body"]
		except:
			return colored("\tERROR: ", "red") + "This version does not exist: " + colored(url,"yellow")

def getPypiChangelog(package, newVersion):
	url = "https://pypi.org/pypi/" + package + "/json"

	#TODO: Error handling and throttling
	response = requests.get(url)
	responseJSON = json.loads(response.text)

	if response.status_code != 200:
		error("Pypi API error. Got status code " + colored(str(response.status_code), "yellow") + " for URL " + colored(url, "yellow"))
	else:
		try:
			sourceCodeURL = responseJSON["info"]["project_urls"]["Source"]
			sourceCodeURL = urllib.parse.urlparse(sourceCodeURL)
			if sourceCodeURL.hostname == "github.com":				
				return getGithubChangelog(sourceCodeURL, newVersion)
			else:
				return warning("\tUnable to fetch changelog for " + colored(package, "yellow") + ". The source code was not hosted on github.")

		except KeyError:
			#TODO: Add an option to allow the user to fill in the source code site
			return warning("\tUnable to get source code site for the " + colored(package, "yellow") + " pypi package.")

def gupCheckForUpgrades(gupOutput):
	"""gupOutput = The output of \"gup check\""""
	packages = []

	for line in gupOutput:
		line = line.strip()
		if line != "gup: INFO: check binary under $GOPATH/bin or $GOBIN":
			if "Already up-to-date" not in line:
				line = re.sub(r".*\[[0-9]*\/[0-9]*\] ", "", line)

				packagelist = re.findall(r".+ \(", line)
				package = packagelist[0]
				package = package[:-2]

				versionList = re.findall(r"\(.*\)", line)
				newVersion = ((re.findall(r"to .*", versionList[0]))[0])[3:-1]
				oldVersion = ((re.findall(r".* to", versionList[0]))[0])[1:-3]
				
				# If a new version is available...
				result = parseVersions(newVersion, oldVersion, package, "gup")
				if result[0]:
					packages.append(package)
				
				if result[1]:
					if package.startswith("github.com"):
						packageList = package.split("/")
						
						if not devMode:
							url = "https://api." + packageList[0] + "/repos/" + packageList[1] + "/" + packageList[2] + "/releases/tags/v" + newVersion

							print(getGithubChangelog(url) + "\n")

					else:
						print("You must manually check the release notes for: " + package)

					

	return packages


# This function receives the output of "pip list --outdated" and a whitelist of which programs to update
def pipIsUpdateAvailable(pipOutput, pipWhitelistedPackages):
	"""pipOutput is the output of \"pip list --outdated\"\n
		pipWhitelistedPackages is the list of packages that will be updated\n
		This function returns an array of the upgradeable packages
		"""
	upgradeablePackages=[]
	for line in pipOutput[2:]:
		package = re.findall(r"^([^\s]+)", line)
		package = package[0]

		if package in pipWhitelistedPackages:
		
			# Regex magic
			oldVersion = re.sub(package + "( )+", "", line)
			newVersion = oldVersion
			oldVersion = re.findall("^([^\s]+)", oldVersion)
			newVersion = re.sub(oldVersion[0] + "( )+", "", newVersion)
			newVersion = re.findall("^([^\s]+)", newVersion)

			# List to string
			newVersion = newVersion[0]
			oldVersion = oldVersion[0]

			# If a new version is available...
			result = parseVersions(newVersion, oldVersion, package, "pip")
			if result[0]:
				upgradeablePackages.append(package)

			if result[1]:
				try:
					changelog = getPypiChangelog(package, newVersion)
					print(changelog + "\n")
				except:
					# If getPypiChangelog returned an error...
					continue
	return upgradeablePackages


def pipUpgradeVenvs(pathToVenv, packageToUpgrade):
	stream = os.popen("cd " + pathToVenv +"\Scripts & activate & pip list --outdated")
	pipOutput = stream.readlines()
	pipWhitelistedPackages = [packageToUpgrade]
	upgradeable = pipIsUpdateAvailable(pipOutput, pipWhitelistedPackages)
	if len(upgradeable) == 1:
		return [pathToVenv, packageToUpgrade]
	else:
		return []

def checkGitRepoUpgrade(path: str) -> bool:
	"""Recieves the folder path of a github cloned repo.\n
	Returns True if an update is available for the supplied repo"""
	stream = os.popen("cd " + path + " && git describe --tags")
	oldVersion = stream.readlines()
	oldVersion = (oldVersion[0]).strip()
	oldVersion = re.sub(r"-[0-9]{1,2}+-([A-z]|[0-9]){6,9}", "", oldVersion)

	stream = os.popen("cd " + path + " && git config --get remote.origin.url")
	remote = stream.readlines()
	remote = (remote[0]).strip()
	remote = urllib.parse.urlparse(remote)

	# Parse URL
	pathList = (remote.path[1:]).split("/") 
	pathListLen = len(pathList)

	#Normally pathListLen would always be equal to 2, but in the rare case where someone put the URL as (for example) "https://github.com/username/repo/", the len will be three, because of that extra slash at the end. This is also done to prevent potential CSRF or token leaks
	if pathListLen == 2 or (pathListLen == 3 and pathList[2] == ""):
		package = pathList[0] + "/" + pathList[1]
		if githubToken != "":
			newVersion = getLatestGithubRelease(remote)

			result = parseVersions(newVersion, oldVersion, package, "git")
			if result[1]:
				package = pathList[0] + "/" + pathList[1]
				url = "https://api.github.com/repos/" + pathList[0] + "/" + pathList[1] + "/releases/tags/v" + newVersion
				changelog = getGithubChangelog(url)
				print(changelog + "\n")
				
			return result[0]

	else:
		warning("The github remote URL for " + colored(package, "yellow") + " is in an unsupported format: " + colored(remote, "yellow"))

def chocoCheckForUpgrades(chocoOutput: str) -> list[str]:
	"""Receives the raw output of \"choco outdated\""""

	chocoUpgradeablePackages = []

	chocoOutput = chocoOutput[4:-3]
	for line in chocoOutput:
		line = line.split("|")
		if not line[0].endswith(".install"):
			result = parseVersions(line[2], line[1], line[0], "choco")

			if result[0]:
				chocoUpgradeablePackages.append(line[0])
			
			if result[1]:
				stream = os.popen("choco info " + line[0])
				packageInfo = stream.readlines()

				#Found the release notes,  
				#[True|False,             url|]
				releaseNotes=[False, ""]

				titles=["Release Notes", " Software Source", "Software Site"]

				for title in titles:
					# If we haven't found the release notes yet...
					if not releaseNotes[0]:
						title = " " + title +": "
						for packageInfoLine in packageInfo:
							if packageInfoLine.startswith(title):
								releaseNotesURL = (packageInfoLine[len(title):]).strip()
								try:
									releaseNotesURLParsed = urllib.parse.urlparse(releaseNotesURL)
									if releaseNotesURLParsed.hostname == "github.com":
										releaseNotes[0] = True
										releaseNotes[1] = getGithubChangelog(releaseNotesURLParsed, line[2])
									else:
										releaseNotes[0] = True
										releaseNotes[1] = "\t" + packageInfoLine.strip()
								except:
									releaseNotes[0] = True
									releaseNotes[1] = "\t" + packageInfoLine.strip()
								break

				if not releaseNotes[0]:
					print("\tRelease notes were not included in the nuspec.")
				else:
					print(releaseNotes[1])

	return chocoUpgradeablePackages

# def npmIsUpdateAvailable(npmWhitelistedPackages: list[str]) -> list[str]:
# 	npmOutput = npmOutput.strip()
# 	npmOutputJSON = json.loads(npmOutput)

# 	if len(npmOutputJSON) == 0:
# 		return

# 	npmUpgradeablePackages = []

# 	for key in npmOutputJSON.keys():
# 		package = str(key)
# 		if package in npmWhitelistedPackages:
# 			oldVersion = npmOutputJSON[key]["current"]
# 			newVersion = npmOutputJSON[key]["wanted"]

# 			# Parse versions that don't comply with semantic versioning
# 			semverNewVersion = forceSemver(newVersion)
# 			semverOldVersion = forceSemver(oldVersion)

# 			if semverNewVersion[1] == Exception or semverOldVersion[1] == Exception:
# 				return False
			
# 			semverNewVersion = semverNewVersion[0]
# 			semverOldVersion = semverOldVersion[0]

# 			if(semverNewVersion > semverOldVersion):
# 				npmUpgradeablePackages.append(package)
			
# 			parseVersions(newVersion, oldVersion, package, "npm")
			
# 	return npmUpgradeablePackages

def runCommand(command: str):
	"""Runs a command and prints out its live output"""
	process = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
	while process.stdout.readable():
		line = process.stdout.readline()
		if not line:
			break
		print(str(line.strip())[1:])

def upgradeGitClone(path: str):
	if not devMode:
		command = "cd " + path + " & git pull"
		print(colored("Running \"" + command + "\"...", "green"))
	else:
		command = "cd " + path + " & git pull --dry-run"
		print(colored("devMode: ", "yellow") + colored("Running \"" + command +"\"...", "green"))
	
	runCommand(command)


############################ END OF FUNCTIONS ##########################

# Update gup packages
if generalUpgradeSettings["gup"]:
	if not devMode:
		stream = os.popen("gup check")
		gupOutput = stream.readlines()
	else:
		gupOutput=["gup: INFO: check binary under $GOPATH/bin or $GOBIN",
		"gup: INFO: [1/6] github.com/gwen001/github-subdomains (Already up-to-date: v1.2.0)",
		"gup: INFO: [2/6] github.com/OJ/gobuster/v3 (Already up-to-date: v3.4.0)"
		"gup: INFO: [3/6] github.com/nao1215/gup (Already up-to-date: v0.15.1)",
		"gup: INFO: [4/6] github.com/j3ssie/metabigor (Already up-to-date: v1.12.1)",
		"gup: INFO: [5/6] github.com/ossf/criticality_score (Already up-to-date: v1.0.7)",
		"gup: INFO: [6/6] github.com/itsignacioportal/hacker-scoper (v1.0.0 to v3.0.0)"]

	gupUpgradeablePackages = gupCheckForUpgrades(gupOutput)

if generalUpgradeSettings["pip"]:
	# Update pip packages 
	pipUpgradeablePackages = []
	pipUpgradeableVenvs = []

	if not devMode:
		stream = os.popen("pip list --outdated")
		pipOutput = stream.readlines()

		pipWhitelistedPackages = ["pip_audit",
		"safety",
		"guessit",
		"srt"]
	else:
		pipOutput = ["Package    Version Latest Type",
		"---------- ------- ------ -----",
		"pip_audit    1.1.2   2.4.14 wheel",
		"minorPackage 2.4.0   2.5.0  wheel",
		"patchPackage 2.5.0   2.5.1  wheel",
		"rich         13.0.1  13.2.0 wheel",
		"setuptools   65.5.0  66.1.1 wheel"]
		pipWhitelistedPackages = ["pip_audit", "minorPackage", "patchPackage"]

	# Check pip upgrades
	pipUpgradeablePackages = pipIsUpdateAvailable(pipOutput, pipWhitelistedPackages)

if generalUpgradeSettings["pipVenvs"]:
	# Check upgrades for pip virtualenvs
	safetyUpgrade = pipUpgradeVenvs("C:\Program Files\HackingSoftware\safetyPythonVenv","safety")
	if len(safetyUpgrade) == 2:
		pipUpgradeableVenvs.append(safetyUpgrade)

if generalUpgradeSettings["git"]:
	# Check upgrades for git repositories
	githubSearchPath = "C:\Program Files\HackingSoftware\github-search"
	githubSearch = checkGitRepoUpgrade(githubSearchPath)

	grauditPath = "C:\Program Files\HackingSoftware\graudit"
	graudit = checkGitRepoUpgrade(grauditPath)

if generalUpgradeSettings["choco"]:
	if not devMode:
		stream = os.popen("choco outdated")
		chocoOutput = stream.readlines()
	else:
		chocoOutput = ["Chocolatey v1.2.1",
		"Outdated Packages",
		" Output is package name | current version | available version | pinned?",
		"",
		"dotnet-7.0-desktopruntime|7.0.1|7.0.2|false",
		"dotnet-desktopruntime|7.0.1|7.0.2|false",
		"ds4windows|3.2.6|3.2.7|false",
		"filezilla|3.62.2|3.63.0|false",
		"Firefox|108.0.1|109.0|false",
		"golang|1.19.4|1.19.5|false",
		"imagemagick|7.1.0.56|7.1.0.57|false",
		"imagemagick.app|7.1.0.56|7.1.0.58|false",
		"nextcloud-client|3.6.4|3.6.6|false",
		"obs-studio|28.1.2|29.0.0|false",
		"obs-studio.install|28.1.2|29.0.0|false",
		"openjdk|19.0.1|19.0.2|false",
		"protonvpn|2.3.1|2.3.2|false",
		"super-productivity|7.12.0|7.12.1|false",
		"teamviewer|15.37.3|15.38.3|false",
		"winscp|5.21.6|5.21.7|false",
		"winscp.install|5.21.6|5.21.7|false",
		"wireshark|4.0.2|4.0.3|false",
		"",
		"Chocolatey has determined 18 package(s) are outdated.",
		""]

	chocoUpgradeablePackages = chocoCheckForUpgrades(chocoOutput)

# if generalUpgradeSettings["npm"]:
# 	npmWhitelistedPackages = ["calculator"]
# 	npmUpgradeablePackages = npmIsUpdateAvailable(npmWhitelistedPackages)

#TODO: add winget support when they fix `winget list`: https://github.com/microsoft/winget-cli/issues/1155

# user@DESKTOP-25GQVRM:~$ sudo apt upgrade
# Reading package lists... Done
# The following packages will be upgraded:
#   sudo
# 1 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
# Need to get 1,061 kB of archives.
# After this operation, 0 B of additional disk space will be used.
# Do you want to continue? [Y/n]

upgradeablePackages = []

if generalUpgradeSettings["gup"]:
	upgradeablePackages += gupUpgradeablePackages

if generalUpgradeSettings["pip"]:
	upgradeablePackages += pipUpgradeablePackages

if generalUpgradeSettings["pipVenvs"]:
	upgradeablePackages += pipUpgradeableVenvs

if generalUpgradeSettings["git"]:
	if githubSearch:
		upgradeablePackages.append("githubSearch")
	if graudit:
		upgradeablePackages.append("graudit")

if generalUpgradeSettings["choco"]:
	upgradeablePackages += chocoUpgradeablePackages

# if generalUpgradeSettings["npm"]:
# 	upgradeablePackages += npmUpgradeablePackages


print("Need to upgrade " + colored(len(upgradeablePackages), "yellow") + " packages.")
print("\t" + colored(str(numberOfMajorUpgrades) + " MAJOR upgrades", "green"))
print("\t" + colored(str(numberOfMinorUpgrades) + " Minor upgrades", "blue"))
print("\t" + str(numberOfPatchUpgrades) + " Patch upgrades")
userWantsToUpdate = (input("Do you want to continue? [Y/n] ")).lower()

# generalUpgradeSettings={
# 	"gup": True,
# 	"pip": True,
# 	"pipVenvs": True,
# 	"git": True,
# 	"choco": True,
# 	"npm": True
# }
if userWantsToUpdate == "" or userWantsToUpdate.startswith("y"):
	
	# Upgrade go packages
	# Putting a list in an if checks if its empty
	if generalUpgradeSettings["gup"] and gupUpgradeablePackages:
		if not devMode:
			print(colored("Running \"gup update\"...", "green"))
			command = "gup update"
		else:
			print(colored("devMode: ", "yellow") + colored("Running \"gup update --dry-run\"...", "green"))
			command = "gup update --dry-run"

		runCommand(command)

	# Upgrade whitelisted pip packages
	# Putting a list in an if checks if its empty
	if generalUpgradeSettings["pip"] and pipUpgradeablePackages:
		pipUpgradeablePackages = " ".join(pipUpgradeablePackages)
		if not devMode:
			command = "pip install --upgrade " + pipUpgradeablePackages
			print(colored("Running \"" + command + "\"...", "green"))
		else:
			command = "pip install --upgrade --dry-run " + pipUpgradeablePackages
			print(colored("devMode: ", "yellow") + colored("Running \"" + command +"\"...", "green"))

		runCommand(command)
		
	# Upgrade python venvs
	if generalUpgradeSettings["pipVenvs"]:
		for venv in pipUpgradeableVenvs:
			pathToVenv = venv[0]
			package = venv[1]

			if not devMode:
				command = "cd " + pathToVenv + "\Scripts & activate & pip install --upgrade " + package
				print(colored("Running \"" + command + "\"...", "green"))
			else:
				command = "cd " + pathToVenv + "\Scripts & activate & pip install --upgrade --dry-run " + package
				print(colored("devMode: ", "yellow") + colored("Running \"" + command +"\"...", "green"))

			runCommand(command)

	# Upgrade git clones
	if generalUpgradeSettings["git"]:
		if githubSearch:
			upgradeGitClone(githubSearchPath)
		if graudit:
			upgradeGitClone(grauditPath)
		
	# Upgrade chocolatey packages
	if generalUpgradeSettings["choco"]:
		if not devMode:
			command = "choco upgrade all"
			print(colored("Running \"" + command + "\"...", "green"))
		else:
			command = "choco upgrade --noop all"
			print(colored("devMode: ", "yellow") + colored("Running \"" + command +"\"...", "green"))

		runCommand(command)

	# # Upgrade npm packages
	# if generalUpgradeSettings["npm"]:
	# 	for package in npmUpgradeablePackages:
	# 		if not devMode:
	# 			command = "npm update " + package
	# 			print(colored("Running \"" + command + "\"...", "green"))
	# 		else:
	# 			command = "npm update --dry-run " + package
	# 			print(colored("devMode: ", "yellow") + colored("Running \"" + command +"\"...", "green"))

	# 		runCommand(command)

print(colored("==================================================", "green"))
print(colored("                      ALL DONE!                   ", "green"))
print(colored("==================================================", "green"))