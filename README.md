# FUpdate

A windows package-manager manager. This Python 3.11.1 script supports [Chocolatey](https://chocolatey.org/), [pip](https://www.python.org/), [python venvs](https://docs.python.org/3/library/venv.html), [gup](https://github.com/nao1215/gup) and repositories that have been cloned via `git clone`.

## Features

- Gets the changelog for the upgraded packages depending on user settings:
```python
versionNotificationSettings={
	"Major Versions": True,
	"Minor Versions": False,
	"Patch Versions": False
	}
```
- Get number of total upgrades, with individual indicators for:
	- Major upgrades
	- Minor upgrades
	- Patch upgrades

## Demo video

[![Clickable image that goes to a demo of fupdate](https://img.youtube.com/vi/b2pJXapwRVQ/0.jpg)](https://www.youtube.com/watch?v=b2pJXapwRVQ)

## Installation
```
git clone https://github.com/ItsIgnacioPortal/fupdate
cd fupdate
python fupdate.py
```
NOTE: Consider adding fupdate as a git repo to be updated in the script.
