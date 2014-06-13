# Licensed under a 3-clause BSD style license - see LICENSE

from .import_modules import *
from . import Grid, Misc, Series


##----- ----- ----- ----- ----- ----- ----- ----- ----- -----##
## Contain functions to perform tasks related to passband
## filters, such as flux integration.
##----- ----- ----- ----- ----- ----- ----- ----- ----- -----##


def Band_integration(band_func, w, f, nu=False, AB=True):
    """
    Integrate a spectrum over a filter response curve.
    
    band_func: function that interpolates the filter response at a given
        set of wavelengths/frequencies.
    w: wavelengths or frequencies of the source to be integrated in wavelength
        or frequency space.
        wavelengths must be in angstrom.
        wavelengths must be in hz.
    f: flux density in erg/s/cm^2/A or erg/s/cm^2/Hz.
    nu: Whether the input values are in the frequency or wavelength domain
    AB: Whether the integration should be performed in the STMAG system
        or the ABMAG system.
        (see equation 5,6 from Linnell, DeStefano & Hubeny, ApJ, 146, 68)
    
    See The Alhambra Photometric System (doi:10.1088/0004-6256/139/3/1242) for more details.
    See also The Mauna Kea Observatories Near-Infrared Filter Set. III. Isophotal Wavelengths and Absolute Calibration (doi:10.1086/429382).
    """
    f_band = band_func(w)
    if nu:
        nu, f_nu = w, f
    else:
        ## Make units m instead of A to simplify calculations
        wav, f_wav = w*1e-10, f*1e10
    ## Check if we work in the AB system (F_nu)
    if AB:
        ## The following equation is from Bessell & Murphy 2012 (eq. 2)
        if np.any(nu):
            f_int = scipy.integrate.trapz(f_band*f_nu/nu, nu) / scipy.integrate.trapz(f_band/nu, nu)
        ## The following equation is from Bessell & Murphy 2012 (eq. 2)
        else:
            f_int = scipy.integrate.trapz(f_band*f_wav*wav, wav) / scipy.integrate.trapz(f_band/wav*cts.c, wav)
    ## If not we work in the ST system (F_lambda)
    else:
        if np.any(nu):
            f_int = scipy.integrate.trapz(f_band*f/w, w) / scipy.integrate.trapz(f_band*cts.c/w**3,w)
        ## The following equation is from Linnell, DeStefano & Hubeny 2013 (eq. 6)
        else:
            f_int = scipy.integrate.trapz(f_band*f*w, w) / scipy.integrate.trapz(f_band*w,w)
        ## For the ST system (F_lambda), we convert from A to m
        f_int = f_int * 1e-10
    return f_int

def Doppler_boosting_factor(spectrum, bandpass, wavelengths, maxv=500e3, deltav=1e3, verbose=False):
    """Doppler_boosting_factor(spectrum, bandpass, wavelengths, maxv=500e3, deltav=1e3, verbose=False)
    This function calculates the Doppler boosting factor of a spectrum
    given a certain bandpass. Both spectrum and banpass must be sampled
    at the provided wavelengths values.

    spectrum (array): spectrum
    bandpass (array): bandpass of the filter
    wavelengths (array): wavelengths of the spectrum and bandpass
    maxv (float): maximum value for the Doppler shift to be sampled in m/s
    deltav (float): Doppler shift sampling in m/s
    verbose (bool): If true, will display the a plot of the fit for the Doppler boosting.
    """
    vels = np.arange(-maxv, maxv+deltav, deltav)
    wav0 = wavelengths[0]
    deltawav0 = wavelengths[1] - wavelengths[0]
    intflux = []
    for v in vels:
        spectrum_shifted = Grid.Shift_spectrum(spectrum, wavelengths, v, wav0, deltawav0)
        #intflux.append( np.sum(spectrum_shifted*bandpass*wavelengths*np.sqrt( (1-v/299792458.0)/(1+v/299792458.0) )**5) )
        intflux.append( np.sum(spectrum_shifted*bandpass*wavelengths / (1-v/cts.c)**5) )
    if verbose:
        plotxy(spectrum/spectrum.max(), wavelengths, rangey=[0,1.05])
        plotxy(bandpass/bandpass.max(), wavelengths, color=2)
        nextplotpage()
    intflux = np.array(intflux)
    intflux /= intflux[intflux.size/2]
    tmp = Misc.Fit_linear(intflux, x=vels/cts.c, b=1., output=verbose, inline=True)
    boost = tmp[1]
    return boost

def Load_filter(band_fln, nu=True):
    """ Load_filter(band_fln, nu=True)
    Returns a function that interpolates the filter response at a given
    wavelength/frequency.
    
    band_fln: filter filename.
        The format should be two columns (wavelengths in A, response)
        The wavelengths must be in ascending order.
    nu (True): Whether the filter response should be converted to the frequency
        domain or to remain in the wavelength domain.
    """
    # Load the pass band data, first column is wavelength in A, second column is transmission
    w_filter, t_filter  = np.loadtxt(band_fln, unpack=True)[:2]
    # The Bessell filter data are in nm, so need to multiply by 10
    #if band_fln.find('bessell') != -1:
    #    w_filter *= 10
    # Check if we work in the AB system (F_nu) or ST system (F_lambda)
    if nu:
        t_filter = t_filter[::-1]
        w_filter = cts.c / (w_filter[::-1] * 1e-10) # [w_filter] = Hz
    # Define an interpolation function, such that the atmosphere data can be directly multiplied by the pass band.
    band_func = scipy.interpolate.interp1d(w_filter, t_filter, kind='cubic', bounds_error=False, fill_value=0.)
    return band_func

def Resample_spectrum(w, f, wrange=None, resample=None):
    """
    Takes a spectrum f and the associated wavelengths/frequencies
    and trim it off and resample it as constant intervals.
    
    w (array): spectral wavelengths/frequencies
    f (array): spectral fluxes
    wrange (list): minimum and maximum value to trim the spectrum at.
        The range is inclusive of the trim values.
        If None, will preserve the current limits.
    resample (float): new sampling interval, in the same units as the
        w parameter. If None, not resampling is done (thus only trimming).
    """
    ## We may want to resample the spectrum at a given resolution.
    if wrange is not None:
        inds = (w>=wrange[0])*(w<=wrange[1])
        w = w[inds]
        f = f[inds]
    if resample is not None:
        ## Because np.arange does not include the last point, we need to add
        ## half the resampling size to catch the last element in case it falls on.
        w_new = np.arange(w[0], w[-1]+resample*0.5, resample)
        weight, pos = Series.Getaxispos_vector(w, w_new)
        f_new = f[pos]*(1-weight) + f[pos+1]*weight
        f = f_new
        w = w_new
    return w, f

def W_effective(band_func, w, nu=True):
    """ W_effective(band_func, w, nu=True)
    
    band_func: function that interpolates the filter response at a given
        set of wavelengths/frequencies.
    w: wavelengths or frequencies of the source to be integrated in A or Hz.
    nu (True): Whether the integration should be performed in the frequency
        or wavelength domain.
    
    See The Alhambra Photometric System (doi:10.1088/0004-6256/139/3/1242) for more details.
    See also The Mauna Kea Observatories Near-Infrared Filter Set. III. Isophotal Wavelengths and Absolute Calibration (doi:10.1086/429382).
    """
    ## The following equation is from Bessell & Murphy 2012 (eq. A5)
    f_band = band_func(w)
    f_int = scipy.integrate.trapz(f_band*w, w) / scipy.integrate.trapz(f_band,w)
    return f_int


