# Jocular

Jocular is a tool for *Electronically-Assisted Astronomy* (EEA).

Jocular supports the observation of astronomical objects in near real-time by connecting up a camera to a telescope or suitable lens. It also supports session-planning through extensive deep sky object (DSO) databases, helps to manage your captures, and
enables the reloading of previously-captured images.

Jocular is a cross-platform application. It has been used extensively on OSX and Windows but ought to work on Linux variants too. 

This is the first public release although the application has been in use for some time. Further documentation will be added over the coming days.

### Requirements

Jocular requires a recent Python 3 system. To check whether you already have a suitable system, open a command window (Windows) or terminal (OSX/Linux) and type

	python --version

If the version is 3.4 or later you are all ready. If not, visit <python.org> to download a version appropriate for your operating system.

### Installation

In your command or terminal window, type:

	pip install jocular

This will install both Jocular and its dependencies. The process may take a minute or more during which you will see lots of diagnostic lines appearing.

### Running

To test whether you can run Jocular, simply type

	jocular

The first time Jocular runs it will ask you to run again, supplying a *data directory*. This is the place where Jocular will store all your captures, calibration files, observing lists and the like. The directory must exist so go ahead and create a directory wherever you like, named however you wish e.g. `joculardata'. Then run 

	jocular --datadir <PATH>

where `<PATH>' is the location of your datadir.

The first time Jocular runs it will take about 30-60s to compile all its necessary scripts. This is normal. Eventually a window that looks like this will appear:

![Jocular starting screen](images/startup_screen.jpg)





