# Adding your own DSO catalogues

You can add your own DSO catalogues to Jocular. Simply create a comma-separated value file with the following format

```
Name,RA,Dec,Con,OT,Mag,Diam,Other
NGC 5,1.953750,35.362330,AND,GX,14.71,0.977,E
NGC 7836,2.006850,33.070780,AND,GX,14.36,0.891,E?
NGC 11,2.177100,37.447840,AND,GX,14.44,1.445,Sa
NGC 20,2.386200,33.308610,AND,GX,14.21,1.738,E-S0
NGC 13,2.198850,33.433380,AND,GX,14.11,2.291,Sb
NGC 19,2.670300,32.983110,AND,GX,14.00,1.202,SBbc

```

name it with the `.csv` extension, and drop it into the `catalogues` sub-directory of your joculardata directory.

Note that 

* `RA` and `Dec` are in decimal degrees (i.e. RA runs from 0 to 360 and Dec from -90 to +90)
* `Con` is a 3-letter constellation code
* `OT` is a 2- or 3-letter object type code
* `Mag` is magnitude
* `Diam` is the object's diameter in the longest direction, in arcminutes
* `Other` is an arbitrary string that can be used to report interesting properties

