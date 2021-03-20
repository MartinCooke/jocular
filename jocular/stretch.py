''' Various stretch functions. Easy to add more. Room for refinement,
    methinks.
'''

import numpy as np

def stretch(x, method='linear', param=None, NR=0, background=None):

    # if no noise reduction just use stretch alone
    if (NR <= 0) or (background is None):
        return stretch_main(x, method=method, param=param)

    else:
        # get stretched data and lightly suppress low end
        y = stretch_main(x, method=method, param=param)
        hyper_param = 1 - .1 * (NR / 100)
        return y * stretch_main(x, method='hyper', param=hyper_param)

def stretch_main(x, method='linear', param=None):

    if method == 'linear':
        return x

    if method == 'hyper':
        d = .02
        c = d * (1 + d - param)
        return (1 + c) * (x / (x + c))

    if method == 'log':
        c = param * 200
        return np.log(c*x + 1) / np.log(c + 1)

    if method == 'asinh':
        # c = param * 250
        c = param * 2000
        return np.arcsinh(c*x) / np.arcsinh(c + .0000001)

    if method == 'gamma':
        # with noise reduction linear from x=0-a, with slope s
        y = x.copy()
        # g = .5 - .5 * param
        g = .75 - .75 * param
        a0 = .01
        s = g / (a0 * (g - 1) + a0 ** (1 - g))
        d = (1 / (a0 ** g * (g - 1) + 1)) - 1
        y[x < a0] = x[x < a0] * s
        y[x >= a0] =  (1 + d) * (x[x >= a0] ** g) - d
        return y
    
    else:
        return x

