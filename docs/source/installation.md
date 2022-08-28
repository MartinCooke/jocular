# Installation

Installation is generally a straightforward process taking a few minutes, but if you come across any problems, check out [the troubleshooting section](troubleshootinginstallation).

## Step 1. Check that you have Python on your system

Jocular requires Python (v3.6 - v3.9, but not v 3.10). Check whether you have Python on your system by opening a command/terminal window and typing:

```
python --version
```

If you don't have a suitable Python version, download it from [python.org](https://python.org). 

```{admonition} Windows
:class: warning

during installation you will be asked whether you want Python to be on your PATH: the answer is yes.
```

:::{note}
I recommend that you close the terminal window that you used to check for the existence of Python and re-open after installing Python so that any changes to the PATH are picked up.
:::

## Step 2. Install Jocular

To install Jocular and its dependencies, open a terminal/command window and type

```
pip install jocular
```

This takes a few minutes as various dependencies are downloaded.

```{admonition} Note for existing Python users
If you are an existing Python user/developer, you might prefer to install Jocular in a [virtual environment](https://docs.python.org/3/tutorial/venv.html)
```

## Step 3. Create a data directory

If you are using Jocular for the first time, before running the program you should create a directory where Jocular can store your captures and other files such as calibration files and catalogues. You can call this directory whatever you like, but ```joculardata``` makes a lot of sense; indeed, in other parts of this document we'll refer to this as your ```joculardata``` directory. 

## Step 4. Run Jocular

To run jocular, simply type

```
jocular
```

The first time the program runs it will ask you to locate the ```joculardata``` directory. You'll find also that it takes some time to start up (perhaps up to a minute) the first time round, but subsequent startups are much faster!


(upgrading)=
## Upgrading Jocular to the latest version

Jocular is being developed continuously. To upgrade to the latest release, type

```
pip install --upgrade jocular
```

(downgrading)=
## Downgrading to a specific version

If you run into any issues with the latest version, it is easy to downgrade to an earlier working version by specifying the version number like this:

```
pip install --upgrade jocular==0.5.4
```

(troubleshootinginstallation)=
## Troubleshooting

### All operating systems

* If you run into problems with the ```pip``` commands, try ```pip3``` instead. Some systems come with an earlier version of Python installed; pip3 ensures that Python v3 is used.

* The default ```pip install``` command installs Jocular system-wide. If you come across a permissions issue, try the following form, which installs Jocular for you alone:

```
pip install jocular --user
```

### Mac

* If you are unable to connect to any camera, check that you have ```libusb-1.0.0.dylib``` on your system. If you don't have it already, it can be built using

```
brew install libusb
```

:::{note}
it appears you have to build libusb **before** installing Jocular; you can uninstall Jocular if you need to using the command ```pip uninstall jocular```
:::


### Windows

* Some users have reported problems with the updated widgets; if you get error messages that mention ```kivy``` or ```kivymd``` you should revert back to the earlier version of the GUI widgets like this:

```
pip install kivymd==0.104.2
```

* If you are unable to connect to your ASI camera you probably need to install the driver from [the ZWO website](https://astronomy-imaging-camera.com/software-drivers)





