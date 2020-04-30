# -*- coding: utf-8 -*-

"""WAVELET MODULE

This module contains methods for performing wavelet transformations using iSAP

:Author: Samuel Farrens <samuel.farrens@cea.fr>

Notes
-----
This module serves as a wrapper for the wavelet transformation code
`mr_transform`, which is part of the Sparse2D package in iSAP. This executable
should be installed and built before using these methods.

Sparse2D Repository: https://github.com/CosmoStat/Sparse2D

"""

import numpy as np
import subprocess as sp
from os import remove
from random import getrandbits
from datetime import datetime
from modopt.base.np_adjust import rotate_stack
from modopt.interface.errors import is_executable
from modopt.math.convolve import convolve
try:
    from astropy.io import fits
except ImportError:  # pragma: no cover
    import_astropy = False
else:
    import_astropy = True


def execute(command_line):
    """ Execute

    This method executes a given command line.

    Parameters
    ----------
    command_line : str
        The command line to be executed

    Returns
    -------
    tuple
        Stdout and stderr (both type str)

    Raises
    ------
    TypeError
        For invalid input type

    """

    if not isinstance(command_line, str):
        raise TypeError('Command line must be a string.')

    command = command_line.split()

    process = sp.Popen(command, stdout=sp.PIPE, stderr=sp.PIPE)
    stdout, stderr = process.communicate()

    return stdout.decode('utf-8'), stderr.decode('utf-8')


def call_mr_transform(data, opt='', path='./',
                      remove_files=True):  # pragma: no cover
    r"""Call mr_transform

    This method calls the iSAP module mr_transform

    Parameters
    ----------
    data : numpy.ndarray
        Input data, 2D array
    opt : list or str, optional
        Options to be passed to mr_transform (default is '')
    path : str, optional
        Path for output files (default is './')
    remove_files : bool, optional
        Option to remove output files (default is ``True``)

    Returns
    -------
    numpy.ndarray
        Results of mr_transform

    Raises
    ------
    ValueError
        If the input data is not a 2D numpy array

    Examples
    --------
    >>> from modopt.signal.wavelet import *
    >>> a = np.arange(9).reshape(3, 3).astype(float)
    >>> call_mr_transform(a)
    array([[[-1.5       , -1.125     , -0.75      ],
            [-0.375     ,  0.        ,  0.375     ],
            [ 0.75      ,  1.125     ,  1.5       ]],
    <BLANKLINE>
           [[-1.5625    , -1.171875  , -0.78125   ],
            [-0.390625  ,  0.        ,  0.390625  ],
            [ 0.78125   ,  1.171875  ,  1.5625    ]],
    <BLANKLINE>
           [[-0.5859375 , -0.43945312, -0.29296875],
            [-0.14648438,  0.        ,  0.14648438],
            [ 0.29296875,  0.43945312,  0.5859375 ]],
    <BLANKLINE>
           [[ 3.6484375 ,  3.73632812,  3.82421875],
            [ 3.91210938,  4.        ,  4.08789062],
            [ 4.17578125,  4.26367188,  4.3515625 ]]], dtype=float32)

    """

    if not import_astropy:
        raise ImportError('Astropy package not found.')

    if (not isinstance(data, np.ndarray)) or (data.ndim != 2):
        raise ValueError('Input data must be a 2D numpy array.')

    executable = 'mr_transform'

    # Make sure mr_transform is installed.
    is_executable(executable)

    # Create a unique string using the current date and time.
    unique_string = (datetime.now().strftime('%Y.%m.%d_%H.%M.%S') +
                     str(getrandbits(128)))

    # Set the ouput file names.
    file_name = path + 'mr_temp_' + unique_string
    file_fits = file_name + '.fits'
    file_mr = file_name + '.mr'

    # Write the input data to a fits file.
    fits.writeto(file_fits, data)

    if isinstance(opt, str):
        opt = opt.split()

    # Prepare command and execute it
    command_line = ' '.join([executable] + opt + [file_fits, file_mr])
    stdout, stderr = execute(command_line)

    # Check for errors
    if any(word in stdout for word in ('bad', 'Error')):

        remove(file_fits)
        raise RuntimeError('{} raised following exception: "{}"'
                           ''.format(executable, stdout.rstrip('\n')))

    # Retrieve wavelet transformed data.
    result = fits.getdata(file_mr).astype(data.dtype)

    # Remove the temporary files.
    if remove_files:
        remove(file_fits)
        remove(file_mr)

    # Return the mr_transform results.
    return result


def _trim_filter(filter_array):
    """Trim the filters to the minimal size

    This method will get rid of the extra zero coefficients in the filter.

    Parameters
    ----------
    filter_array: numpy.ndarray
        The filter to be trimmed

    Returns
    -------
    numpy.ndarray
        Trimmed filter

    """
    non_zero_indices = np.array(np.where(filter_array != 0))
    min_idx = np.min(non_zero_indices, axis=-1)
    max_idx = np.max(non_zero_indices, axis=-1)
    return filter_array[min_idx[0]:max_idx[0] + 1, min_idx[1]:max_idx[1] + 1]


def get_mr_filters(data_shape, opt='', coarse=False,
                   trim=True):  # pragma: no cover
    """Get mr_transform filters

    This method obtains wavelet filters by calling mr_transform.

    Parameters
    ----------
    data_shape : tuple
        2D data shape
    opt : list, optional
        List of additonal mr_transform options (default is '')
    coarse : bool, optional
        Option to keep coarse scale (default is ``False``)
    trim: bool, optional
        Option to trim the filters down to their minimal size
        (default is ``True``)

    Returns
    -------
    numpy.ndarray
        3D array of wavelet filters

    """

    # Adjust the shape of the input data.
    data_shape = np.array(data_shape)
    data_shape += data_shape % 2 - 1

    # Create fake data.
    fake_data = np.zeros(data_shape)
    fake_data[tuple(zip(data_shape // 2))] = 1

    # Call mr_transform.
    mr_filters = call_mr_transform(fake_data, opt=opt)

    if trim:
        mr_filters = np.array([_trim_filter(f) for f in mr_filters])

    # Return filters
    if coarse:
        return mr_filters
    else:
        return mr_filters[:-1]


def filter_convolve(data, filters, filter_rot=False, method='scipy'):
    r"""Filter convolve

    This method convolves the input image with the wavelet filters.

    Parameters
    ----------
    data : numpy.ndarray
        Input data, 2D array
    filters : numpy.ndarray
        Wavelet filters, 3D array
    filter_rot : bool, optional
        Option to rotate wavelet filters (default is `False`)
    method : {'astropy', 'scipy'}, optional
        Convolution method (default is 'scipy')

    Returns
    -------
    numpy.ndarray
        Convolved data

    Examples
    --------
    >>> from modopt.signal.wavelet import filter_convolve
    >>> x = np.arange(9).reshape(3, 3).astype(float)
    >>> y = np.arange(36).reshape(4, 3, 3).astype(float)
    >>> filter_convolve(x, y)
    array([[[  174.,   165.,   174.],
            [   93.,    84.,    93.],
            [  174.,   165.,   174.]],
    <BLANKLINE>
           [[  498.,   489.,   498.],
            [  417.,   408.,   417.],
            [  498.,   489.,   498.]],
    <BLANKLINE>
           [[  822.,   813.,   822.],
            [  741.,   732.,   741.],
            [  822.,   813.,   822.]],
    <BLANKLINE>
           [[ 1146.,  1137.,  1146.],
            [ 1065.,  1056.,  1065.],
            [ 1146.,  1137.,  1146.]]])

    >>> filter_convolve(y, y, filter_rot=True)
    array([[ 14550.,  14586.,  14550.],
           [ 14874.,  14910.,  14874.],
           [ 14550.,  14586.,  14550.]])

    """

    if filter_rot:
        return np.sum([convolve(coef, f, method=method) for coef, f in
                       zip(data, rotate_stack(filters))], axis=0)

    else:
        return np.array([convolve(data, f, method=method) for f in filters])


def filter_convolve_stack(data, filters, filter_rot=False, method='scipy'):
    r"""Filter convolve

    This method convolves the a stack of input images with the wavelet filters

    Parameters
    ----------
    data : numpy.ndarray
        Input data, 3D array
    filters : numpy.ndarray
        Wavelet filters, 3D array
    filter_rot : bool, optional
        Option to rotate wavelet filters (default is ``False``)
    method : {'astropy', 'scipy'}, optional
        Convolution method (default is 'scipy')

    Returns
    -------
    numpy.ndarray
        Convolved data

    Examples
    --------
    >>> from modopt.signal.wavelet import filter_convolve_stack
    >>> x = np.arange(9).reshape(3, 3).astype(float)
    >>> filter_convolve(x, x)
    array([[[   4.,    1.,    4.],
            [  13.,   10.,   13.],
            [  22.,   19.,   22.]],
    <BLANKLINE>
           [[  13.,   10.,   13.],
            [  49.,   46.,   49.],
            [  85.,   82.,   85.]],
    <BLANKLINE>
           [[  22.,   19.,   22.],
            [  85.,   82.,   85.],
            [ 148.,  145.,  148.]]])

    """

    # Return the convolved data cube.
    return np.array([filter_convolve(x, filters, filter_rot=filter_rot,
                    method=method) for x in data])
