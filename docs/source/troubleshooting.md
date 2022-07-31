# Troubleshooting

## General approaches

To get some feedback on what is happening in your image, toggle the **status panel** at the lower right of the application. This provides a dynamically-updated view for some of the main processes (e.g., stacking, calibration, platesolving, capture).

Jocular creates **log files** that can be found in the `logs` subdirectory of your jocular data directory. These sometimes provide useful information in the case of problems arising.

## Specific issues and possible solutions

* **The platesolver isn't working**. 
	* Check that the image is flipped correctly. 
	* Check that you have entered the scope's focal length and the camera's pixel height. 

* **Jocular is not reacting to images placed in the watched folder** 
	* Do the FITS end up in the `invalid` directory of the watched folder? This may indicate an issue with the FITS files. 
	* Do they get placed in the `unused` subdirectory of watched? In this case check that you are not inadvertently controlling the watched folder using Jocular's capture button (set `control using Jocular` on the watched dir settings panel to off)

* **Jocular is interpreting my darks/flats as lights**
	* Check the `sub type` option in the watched dir settings panel

* **Jocular is providing an incorrect exposure time**
	* This most likely indicates that the capture program does not write exposure to the FITS. A fix is to set `exposure` to `from user` and supply the exposure manually on the main interface
	* Alternatively, the capture program might be using a FITS header for exposure that is non-standard. Use the above fix, but also contact me so that I can add this keyword to FITS-handling.

* **Jocular does not recognise the filter I'm using**
	* See above, replacing exposure or sub type with filter.


* **The DSO planner shows incorrect altitude and azimuth for objects**
	* have you entered your latitude and longitude (on the Observatory settings panel)?

* **My images are not being aligned**
	* check the star-extraction settings on the aligner; the `DoG` method is slower but more robust, and setting `bin image` to 1 is also slower but more robust

* **Some of my previous observations are not showing up**
	* click on `rebuild observations` in the previous observations table (and wait -- it an take a while if you have a lot of observations)

* **Help! I deleted some previous observations or calibration files by mistake**
	* Jocular doesn't delete observations/calibration files but instead moves them to the `deleted` directory that you'll find in joculardata. You will have to rename and move them back manually to the right place in either the `captures` directory structure or the `calibration` directory respectively. 

* **Jocular is saving too many FITS and filling up my disk**
	* From time to time, select the DSOs you want to delete in the previous observations table, hit `move to delete dir`, and then manually delete the contents of the `deleted` directory