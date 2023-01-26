import os
import re
import semver
import requests
import json
from termcolor import colored
from urllib.parse import urlparse

"""
1. Get list of all outdated packages
2. If a package has upgraded a major version number, show changelog
3. "Do you want to updated X packages? [Y/n]: "
4. Update everything
"""

devMode = True


def error(message):
	print(colored("ERROR: ", "red") + message)

def warning(message):
	print(colored("WARNING: ", "yellow") + message)

# Setup githubtoken
try:
	githubToken = os.environ["fupdate-github-token"]
except KeyError:
	warning("No github token detected. Please set the environment variable " + colored("fupdate-github-token") + " to your github personal access token. Without it, we can't fetch the changelogs.")
	githubToken = ""

def stripLeadingV(version):
	if version.startswith("v"):
		return version[1:]
	else:
		return version

def getGithubChangelog(url):
	if githubToken != "":
		headers = {"Accept": "application/vnd.github+json", "Authorization": "Bearer " + githubToken, "X-GitHub-Api-Version": "2022-11-28"}
		
		#TODO: Error handling and throttling
		response = requests.get(url, headers=headers)

		responseJSON = json.loads(response.text)

		try:
			return responseJSON["body"]
		except:
			return colored("ERROR: ", "red") + "This version does not exist: " + colored(url,"yellow")

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
			sourceCodeURL = urlparse(sourceCodeURL)
			if sourceCodeURL.hostname == "github.com":				
				pathList = (sourceCodeURL.path[1:]).split("/") 
				pathListLen = len(pathList)

				#Normally pathListLen would always be equal to 2, but in the rare case where someone put the URL as (for example) "https://github.com/username/repo/", the len will be three, because of that extra slash at the end. This is also done to prevent potential CSRF or token leaks
				if pathListLen == 2 or pathListLen == 3:
					# url = "https://api." + packageList[0] + "/repos/" + packageList[1] + "/" + packageList[2] + "/releases/tags/v" + newVersion
					url = "https://api.github.com/repos/" + pathList[0] + "/" + pathList[1] + "/releases/tags/v" + newVersion

					return getGithubChangelog(url)

				else:
					return colored("FATAL ERROR: ", "red") + "The github source code URL for " + colored(package, "yellow") + " was malformed: " + colored(sourceCodeURL, "yellow")

			else:
				return warning("Unable to fetch changelog for " + colored(package, "yellow") + ". The source code was not hosted on github.")

		except KeyError:
			#TODO: Add an option to allow the user to fill in the source code site
			return warning("Unable to get source code site for the " + colored(package, "yellow") + " pypi package.")

def gupIsUpgradeAvailable(gupOutput):
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
				
				newVersion = stripLeadingV(newVersion)

				oldVersion = stripLeadingV(oldVersion)

				semverNewVersion = semver.VersionInfo.parse(newVersion)
				semverOldVersion = semver.VersionInfo.parse(oldVersion)

				if (semverNewVersion > semverOldVersion):
					packages.append(package)
					if(semverNewVersion.major > semverOldVersion.major):
						print(colored("NEW MAJOR VERSION: ", "green") + colored("(gup) ", "yellow") + line)
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

			semverNewVersion = semver.VersionInfo.parse(newVersion)
			semverOldVersion = semver.VersionInfo.parse(oldVersion)

			if(semverNewVersion > semverOldVersion):
				
				upgradeablePackages.append(package)

				#TODO: Add flag to enable show changelog for major, minor and patch releases

				if(semverNewVersion.major > semverOldVersion.major):
					print(colored("NEW MAJOR VERSION: ", "green") + colored("(pip) ", "yellow") + package + " (" + oldVersion + " to " + newVersion + ")")

					try:
						changelog = getPypiChangelog(package, newVersion)
						print(changelog + "\n")
					except:
						# If getPypiChangelog returned an error...
						continue

				elif(semverNewVersion.minor > semverOldVersion.minor):
					print(colored("New minor version: ", "blue") + colored("(pip) ", "yellow") + package + " (" + oldVersion + " to " + newVersion + ")")

				else:
					print("New patch version: " + colored("(pip) ", "yellow") + package + " (" + oldVersion + " to " + newVersion + ")")

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

def checkGitRepoUpgrade(path):
	stream = os.popen("cd " + path + " && git describe --tags")
	oldVersion = stream.readlines()
	oldVersion = (oldVersion[0]).strip()
	oldVersion = stripLeadingV(oldVersion)
	oldVersion = re.sub(r"-[0-9]{1,2}+-([A-z]|[0-9]){6,9}", "", oldVersion)

	stream = os.popen("cd " + path + " && git config --get remote.origin.url")
	remote = stream.readlines()
	remote = (remote[0]).strip()
	remote = urlparse(remote)

	# Parse URL
	pathList = (remote.path[1:]).split("/") 
	pathListLen = len(pathList)

	#Normally pathListLen would always be equal to 2, but in the rare case where someone put the URL as (for example) "https://github.com/username/repo/", the len will be three, because of that extra slash at the end. This is also done to prevent potential CSRF or token leaks
	if pathListLen == 2 or pathListLen == 3:
		#/repos/{owner}/{repo}/releases/latest
		url = "https://api.github.com/repos/" + pathList[0] + "/" + pathList[1] + "/releases/latest"

		package = pathList[0] + "/" + pathList[1]

		if githubToken != "":
			headers = {"Accept": "application/vnd.github+json", "Authorization": "Bearer " + githubToken, "X-GitHub-Api-Version": "2022-11-28"}
			
			#TODO: Error handling and throttling
			response = requests.get(url, headers=headers)

			responseJSON = json.loads(response.text)

			try:
				newVersion = (responseJSON["tag_name"])
			except:
				return colored("ERROR: ", "red") + "This version does not exist: " + colored(url,"yellow")

			newVersion = stripLeadingV(newVersion)

			semverNewVersion = semver.VersionInfo.parse(newVersion)
			semverOldVersion = semver.VersionInfo.parse(oldVersion)

			if(semverNewVersion > semverOldVersion):


				#TODO: Add flag to enable show changelog for major, minor and patch releases

				if(semverNewVersion.major > semverOldVersion.major):
					print(colored("NEW MAJOR VERSION: ", "green") + colored("(git) ", "yellow") + package + " (" + oldVersion + " to " + newVersion + ")")

					url = "https://api.github.com/repos/" + pathList[0] + "/" + pathList[1] + "/releases/tags/v" + newVersion

					changelog = getGithubChangelog(url)
					print(changelog + "\n")
						

				elif(semverNewVersion.minor > semverOldVersion.minor):
					print(colored("New minor version: ", "blue") + colored("(git) ", "yellow") + package + " (" + oldVersion + " to " + newVersion + ")")

				else:
					print("New patch version: " + colored("(git) ", "yellow") + package + " (" + oldVersion + " to " + newVersion + ")")


	else:
		warning("The github remote URL for " + colored(package, "yellow") + " is in an unsupported format: " + colored(remote, "yellow"))


############################ END OF FUNCTIONS ##########################

# Update gup packages

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

gupUpgradeablePackages = gupIsUpgradeAvailable(gupOutput)

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

# Check upgrades for pip virtualenvs
safetyUpgrade = pipUpgradeVenvs("C:\Program Files\HackingSoftware\safetyPythonVenv","safety")
if len(safetyUpgrade) == 2:
	pipUpgradeableVenvs.append(safetyUpgrade)

# Check upgrades for git repositories
checkGitRepoUpgrade("C:\Program Files\HackingSoftware\github-search")

#graudit doesn't use semantic versioning :/
#checkGitRepoUpgrade("C:\Program Files\HackingSoftware\graudit")

"""
choco
npm
microsoft store
winget
"""
