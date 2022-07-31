# Choosing a stretch function

Jocular currently provides 6 different families of stretch functions which differ in the extent to which they boost faint regions at the expense of brighter regions. In order of faint boosting, these are:

* `hyper`
* `asinh`
* `log`
* `gamma`
* `linear`
* `sublin`

The easiest way to appreciate the differences is to explore them all. Just open the stretch panel by clicking on the name of the current stretch in the upper left quadrant and select one stretch after another to judge its effect on the image.

## Some personal preferences

The most useful stretch functions are `log`, `gamma` and `asinh`. `log` is particularly good for globular clusters while `gamma` works well for objects synthesised from monochrome + filters. As a general galaxy stretch, `asinh` boosts fainter regions without too much noise.

To see really faint stuff, perhaps when viewing the image in **negative mode** (recall that this is achieved by double clicking the image), use the `hyper` stretch.

For those objects that are really bright (some planetary nebulae, for example), a `linear` stretch might be useful. There is even a sub-linear stretch (`sublin`) for the occasional tricky object. 

