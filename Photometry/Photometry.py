# Licensed under a 3-clause BSD style license - see LICENSE

__all__ = ["Photometry"]

from ..Utils.import_modules import *
from .. import Utils
from .. import Core
from .. import Atmosphere


######################## class Photometry ########################
class Photometry(object):
    """Photometry
    This class allows to fit the flux from the primary star
    of a binary system, assuming it is heated by the secondary
    (which in most cases will be a pulsar).

    It is meant to deal with photometry data. Many sets of photometry
    data (i.e. different filters) are read. For each data set, one can
    calculate the predicted flux of the model at every data point (i.e.
    for a given orbital phase).
    """
    def __init__(self, atmo_fln, data_fln, ndiv, read=True):
        """__init__(atmo_fln, data_fln, ndiv, read=True)
        This class allows to fit the flux from the primary star
        of a binary system, assuming it is heated by the secondary
        (which in most cases will be a pulsar).

        It is meant to deal with photometry data. Many sets of photometry
        data (i.e. different filters) are read. For each data set, one can
        calculate the predicted flux of the model at every data point (i.e.
        for a given orbital phase).

        atmo_fln (str): A file containing the grid model information for each
            data set. The format of each line of the file is as follows:
                Col 0: band name
                Col 1: band filename
        data_fln (str): A file containing the information for each data set.
            Three formats are currently supported.
            9-column (preferred):
                Col 0: band name
                Col 1: column id for orbital phase. Orbital phases must be 0-1.
                    Phase 0 is defined as the primary star (the one modelled),
                    located at inferior conjunction.
                Col 2: column id for flux/magnitude
                Col 3: column id for flux/magnitude error
                Col 4: shift to phase zero. Sometimes people use other
                    definition for orbital phases, so this allows to correct for
                    it.
                Col 5: band calibration error, in magnitude
                Col 6: softening parameter for asinh magnitude conversion. If
                    the value is 0., then standard magnitudes are used.
                Col 7: flux or mag flag. Currently, all the data must be in the
                    same format.
                    'mag' means magnitude system
                    'flux' means flux system
                Col 8: filename
            8-column (support for asinh magnitudes, no fluxes input):
                Col 0: band name
                Col 1: column id for orbital phase. Orbital phases must be 0-1.
                    Phase 0 is defined as the primary star (the one modelled),
                    located at inferior conjunction.
                Col 2: column id for magnitude
                Col 3: column id for magnitude error
                Col 4: shift to phase zero. Sometimes people use other
                    definition for orbital phases, so this allows to correct for
                    it.
                Col 5: band calibration error, in magnitude
                Col 6: softening parameter for asinh magnitude conversion. If
                    the value is 0., then standard magnitudes are used.
                Col 7: filename
            7-column (only support standard magnitude input):
                Col 0: band name
                Col 1: column id for orbital phase. Orbital phases must be 0-1.
                    Phase 0 is defined as the primary star (the one modelled),
                    located at inferior conjunction.
                Col 2: column id for magnitude
                Col 3: column id for magnitude error
                Col 4: shift to phase zero. Sometimes people use other
                    definition for orbital phases, so this allows to correct for
                    it.
                Col 5: band calibration error, in magnitude
                Col 6: filename
        ndiv (int): The number of surface slice. Defines how coarse/fine the
            surface grid is.
        read (bool): If True, Icarus will use the pre-calculated geodesic
            primitives. This is the recommended option, unless you have the
            pygts package installed to calculate it on the spot.

        >>> fit = Photometry(atmo_fln, data_fln, ndiv, read=True)
        """
        Warning("This is the new Photometry class. Major changes have been done. To use the old one, load the Photometry_legacy module.")

        # We read the data.
        self._Read_data(data_fln)
        # We read the atmosphere models with the atmo_grid class
        self._Read_atmo(atmo_fln)
        # We make sure that the length of data and atmo_dict are the same
        if len(self.atmo_grid) != len(self.data['mag']):
            print 'The number of atmosphere grids and data sets (i.e. photometric bands) do not match!!!'
            return
        else:
            # We keep in mind the number of datasets
            self.ndataset = len(self.atmo_grid)
        # We initialize some important class attributes.
        self._Init_lightcurve(ndiv, read=read)
        self._Setup()

    def Calc_chi2(self, par, offset_free=1, DM=0., AV=0., nsamples=None, influx=False, full_output=False, verbose=False):
        """
        Returns the chi-square of the fit of the data to the model.

        par (list/array): Parameter list as expected by the Make_surface function.
        offset_free (int):
            1) offset_free = 0:
                If the offset is not free and the DM and A_V are specified, the chi2
                is calculated directly without allowing an offset between the data and
                the bands.
                The full chi2 should be:
                    chi2 = sum[ w_i*(off_i-dm-av*C_i)**2]
                        + w_dm*(dm-dm_obs)**2 
                        + w_av*(av-av_obs)**2,     with w = 1/sigma**2
                The extra terms (i.e. dm-dm_obs and av-av_obs) should be included
                as priors.
            1) offset_free = 1:
                The model light curves are fitted to the data with an arbitrary
                offset for each band. After, a post-fit is performed in order to
                adjust the offsets of the curves accounting for the fact that
                the absolute calibration of the photometry may vary.
                Note: The errors should be
                err**2 = calib_err**2 + 1/sum(flux_err)**2
                but we neglect the second term because it is negligeable.
        DM (float): Distance modulus o apply to the data.
            It is possible to specify None in case one would like to allow for
            an arbitrary offset to be optimized for the offset_free = 1 case.
        AV (float): V band extinction.
            It is possible to specify None in case one would like to allow for
            an arbitrary offset to be optimized for the offset_free = 1 case.
        nsamples (int): Number of points for the lightcurve sampling.
            If None, the lightcurve will be sampled at the observed data
            points.
        influx (bool): If true, will calculate the fit between the data and the
            model in the flux domain.
        full_output (bool): If true, will output a dictionnary of additional parameters.
            'offset' (array): the calculated offset for each band.
            'par' (array): the input parameters (useful some get modified.
            'res' (array): the fit residuals.
            'dm' (float): value of the DM.
            'av' (float): value of AV.
        verbose (bool): If true will display the list of parameters and fit information.

        >>> self.Calc_chi2([10.,7200.,PIBYTWO,300e3,1.0,0.9,0.08,4000.,5000.])
        """
        if offset_free == 0:
            # Calculate the fluxes, directly applying the DM and AV
            pred_flux = self.Get_flux(par, flat=True, nsamples=nsamples, verbose=verbose)
            # Fit the data to the fluxes as they are
            diff = self.mag-pred_flux
            ((DM,AV), chi2_data, rank, s) = Utils.Misc.Fit_linear(diff, x=self.ext, err=self.err, b=DM, m=AV)
            residuals = ( diff - (self.ext*AV + DM) ) / self.err
            offset_band = np.zeros(self.ndataset)
            chi2_band = 0.
            chi2 = chi2_data + chi2_band
        else:
            # Calculate the theoretical flux
            pred_flux = self.Get_flux(par, flat=False, nsamples=nsamples, verbose=verbose)
            # Calculate the residuals between observed and theoretical flux
            if influx: # Calculate the residuals in the flux domain
                res1 = np.array([ Utils.Misc.Fit_linear(self.data['flux'][i], x=Utils.Flux.Mag_to_flux(pred_flux[i], flux0=self.atmo_grid[i].flux0), err=self.data['flux_err'][i], b=0., inline=True) for i in np.arange(self.ndataset) ])
                offset_band = -2.5*np.log10(res1[:,1])
                if full_output:
                    print( "Impossible to return proper residuals" )
                    residuals = None
            else: # Calculate the residuals in the magnitude domain
                res1 = np.array([ Utils.Misc.Fit_linear(self.data['mag'][i]-pred_flux[i], err=self.data['err'][i], m=0., inline=True) for i in np.arange(self.ndataset) ])
                offset_band = res1[:,0]
                if full_output:
                    residuals = [ ((self.data['mag'][i]-pred_flux[i]) - offset_band[i])/self.data['err'][i] for i in np.arange(self.ndataset) ]
            chi2_data = res1[:,2].sum()
            # Fit for the best offset between the observed and theoretical flux given the DM and A_V
            res2 = Utils.Misc.Fit_linear(offset_band, x=self.data['ext'], err=self.data['calib'], b=DM, m=AV, inline=True)
            DM, AV = res2[0], res2[1]
            chi2_band = res2[2]
            # Here we add the chi2 of the data from that of the offsets for the bands.
            chi2 = chi2_data + chi2_band
            # Update the offset to be the actual offset between the data and the band (i.e. minus the DM and A_V contribution)
            offset_band -= self.data['ext']*AV + DM

        # Output results
        if verbose:
            print('chi2: {:.3f}, chi2 (data): {:.3f}, chi2 (band offset): {:.3f}, DM: {:.3f}, AV: {:.3f}'.format(chi2, chi2_data, chi2_band, DM, AV))
        if full_output:
            return chi2, {'offset':offset_band, 'par':par, 'res':residuals, 'dm':DM, 'av':AV}
        else:
            return chi2

    def Get_flux(self, par, flat=False, DM=0., AV=0., nsamples=None, verbose=False):
        """
        Returns the predicted flux (in magnitude) by the model evaluated
        at the observed values in the data set.

        par (list/array): Parameter list as expected by the Make_surface function.
        flat (False): If True, the values are returned in a 1D vector.
            If False, predicted values are grouped by data set left in a list.
        DM (float): Distance modulus o apply to the data.
        AV (float): V band extinction.
        nsamples (None): Number of points for the lightcurve sampling.
            If None, the lightcurve will be sampled at the observed data
            points.
        verbose (False): Print some info.

        >>> self.Get_flux([10.,7200.,PIBYTWO,300e3,1.0,0.9,0.08,4000.,5000.])
        """
        # We call Make_surface to make the companion's surface.
        self.Make_surface(par, verbose=verbose)

        # If nsamples is None we evaluate the lightcurve at each data point.
        if nsamples is None:
            phases = self.data['phase']
        # If nsamples is set, we evaluate the lightcurve at nsamples
        else:
            phases = (np.arange(nsamples, dtype=float)/nsamples).repeat(self.ndataset).reshape((nsamples,self.ndataset)).T

        # We take into account flux offset due to the DM and AV.
        if DM is None: DM = 0.
        if AV is None: AV = 0.
        offsets = self.data['ext']*AV + DM

        # Calculate the actual lightcurves
        flux = []
        for i in np.arange(self.ndataset):
                # If we use the interpolation method and if the filter is the same as a previously
                # calculated one, we do not recalculate the fluxes and simply copy them.
                if nsamples is not None and self.grouping[i] < i:
                    flux.append(flux[self.grouping[i]])
                else:
                    flux.append( np.array([self.star.Mag_flux(phase, atmo_grid=self.atmo_grid[i]) for phase in phases[i]]) + offsets[i] )

        # If nsamples is set, we interpolate the lightcurve at nsamples.
        if nsamples is not None:
            for i in np.arange(self.ndataset):
                ws, inds = Utils.Series.Getaxispos_vector(phases[i], self.data['phase'][i])
                flux[i] = flux[i][inds]*(1-ws) + flux[i][inds+1]*ws

        # We can flatten the flux array to simplify some of the calculations in the Calc_chi2 function
        if flat:
            return np.hstack(flux)
        else:
            return flux

    def Get_flux_theoretical(self, par, phases, DM=0., AV=0., verbose=False):
        """
        Returns the predicted flux (in magnitude) by the model evaluated at the
        observed values in the data set.

        par (list/array): Parameter list as expected by the Make_surface function.
        phases: A list of orbital phases at which the model should be
            evaluated. The list must have the same length as the
            number of data sets, each element can contain many phases.
        DM (float): Distance modulus o apply to the data.
        AV (float): V band extinction.
        verbose (False): Print some info.

        Note: tirr = (par[6]**4 - par[3]**4)**0.25

                par.keys() = ['q','porb','incl','k1','omega','filling','tempgrav','temp','tirr']

        >>> self.Get_flux_theoretical([10.,7200.,PIBYTWO,300e3,1.0,0.9,0.08,4000.,5000.])
        """
        # We call Make_surface to make the companion's surface.
        self.Make_surface(par, verbose=verbose)

        # We take into account flux offset due to the DM and AV.
        if DM is None: DM = 0.
        if AV is None: AV = 0.
        offsets = self.data['ext']*AV + DM

        flux = []
        for i in np.arange(self.ndataset):
            # If the filter is the same as a previously calculated one
            # we do not recalculate the fluxes and simply copy them.
            if self.grouping[i] < i:
                flux.append( flux[self.grouping[i]] )
            else:
                flux.append( np.array([self.star.Mag_flux(phase, atmo_grid=self.atmo_grid[i]) for phase in phases[i]]) + offsets[i] )
        return flux

    def Get_Keff(self, par, nphases=20, atmo_grid=0, make_surface=False, verbose=False):
        """
        Returns the effective projected velocity semi-amplitude of the star in m/s.
        The luminosity-weighted average velocity of the star is returned for
        nphases, for the specified dataset, and a sin wave is fitted to them.

        par (list/array): Parameter list as expected by the Make_surface function.
        nphases (int): Number of phases to evaluate the velocity at.
        atmo_grid (int, AtmoGridPhot): The atmosphere grid to use for the velocity
            calculation. Can be an integer that represents the index of the atmosphere
            grid object in self.atmo_grid, and it can be an AtmoGridPhot instance.
        make_surface (bool): Whether lightcurve.make_surface should be called
            or not. If the flux has been evaluate before and the parameters have
            not changed, False is fine.
        verbose (bool): Verbosity. Will plot the velocities and the sin fit.
        """
        # If it is required to recalculate the stellar surface.
        if make_surface:
            self.Make_surface(par, func_par=func_par, verbose=verbose)
        # Deciding which atmosphere grid we use to evaluate Keff
        if isinstance(atmo_grid, int):
            atmo_grid = self.atmo_grid[atmo_grid]
        # Get the Keffs and fluxes
        phases = np.arange(nphases)/float(nphases)
        Keffs = np.array( [self.star.Keff(phase, atmo_grid=atmo_grid) for phase in phases] )
        tmp = Utils.Misc.Fit_linear(Keffs, np.sin(cts.twopi*(phases)), inline=True)
        if verbose:
            pylab.plot(np.linspace(0.,1.), tmp[1]*np.sin(np.linspace(0.,1.)*cts.twopi)+tmp[0])
            pylab.scatter(phases, Keffs)
        Keff = tmp[1]
        return Keff

    def _Init_lightcurve(self, ndiv, read=False):
        """_Init_lightcurve(ndiv, read=False)
        Call the appropriate Lightcurve class and initialize
        the stellar array.

        >>> self._Init_lightcurve(ndiv)
        """
        self.star = Core.Star(ndiv, read=read)
        return

    def Make_surface(self, par, verbose=False):
        """Make_surface(par, func_par=None, verbose=False)
        This function gets the parameters to construct to companion
        surface model and calls the Make_surface function from the
        Lightcurve object.

        par: Parameter list.
            [0]: Mass ratio q = M2/M1, where M1 is the modelled star.
            [1]: Orbital period in seconds.
            [2]: Orbital inclination in radians.
            [3]: K1 (projected velocity semi-amplitude) in m/s.
            [4]: Corotation factor Protation/Porbital.
            [5]: Roche-lobe filling in fraction of x_nose/L1.
            [6]: Gravity darkening coefficient.
                Should be 0.25 for radiation envelopes, 0.08 for convective.
            [7]: Star base temperature at the pole, before gravity darkening.
            [8]: Irradiation temperature at the center of mass location.
                The effective temperature is calculated as T^4 = Tbase^4+Tirr^4
                and includes projection and distance effect.

            Note: Can also be a dictionary:
                par.keys() = ['q','porb','incl','k1','omega','filling','tempgrav','temp','tirr']

        >>> self.Make_surface([10.,7200.,PIBYTWO,300e3,1.0,0.9,0.08,4000.,5000.])
        """
        ## check if we are dealing with a dictionary
        if isinstance(par, dict):
            self.star.Make_surface(
                q        = par['q'],
                porb     = par['porb'],
                incl     = par['incl'],
                k1       = par['k1'],
                omega    = par['omega'],
                filling  = par['filling'],
                tempgrav = par['tempgrav'],
                temp     = par['temp'],
                tirr     = par['tirr']
                )
        else:
            self.star.Make_surface(
                q        = par[0],
                porb     = par[1],
                incl     = par[2],
                k1       = par[3],
                omega    = par[4],
                filling  = par[5],
                tempgrav = par[6],
                temp     = par[7],
                tirr     = par[8]
                )

        if verbose:
            print( "Content on input parameter for Make_surface" )
            print( par )

        return

    def Plot(self, par, nphases=51, offset_free=1, DM=0., AV=0., verbose=True, nsamples=None, output=False):
        """
        Plots the observed and predicted values along with the
        light curve.

        par (list/array): Parameter list as expected by the Make_surface function.
        nphases (int): Orbital phase resolution of the model
            light curve.
        offset_free (int):
            1) offset_free = 0:
                If the offset is not free and the DM and A_V are specified, the chi2
                is calculated directly without allowing an offset between the data and
                the bands.
                The full chi2 should be:
                    chi2 = sum[ w_i*(off_i-dm-av*C_i)**2]
                        + w_dm*(dm-dm_obs)**2 
                        + w_av*(av-av_obs)**2,     with w = 1/sigma**2
                The extra terms (i.e. dm-dm_obs and av-av_obs) should be included
                as priors.
            1) offset_free = 1:
                The model light curves are fitted to the data with an arbitrary offset
                for each band. After, a post-fit is performed in order to adjust the offsets
                of the curves accounting for the fact that the absolute calibration of the
                photometry may vary.
                Note:
                The errors should be err**2 = calib_err**2 + 1/sum(flux_err)**2
                but we neglect the second term because it is negligeable.
        DM (float): Distance modulus o apply to the data.
            It is possible to specify None in case one would like to allow for
            an arbitrary offset to be optimized for the offset_free = 1 case.
        AV (float): V band extinction.
            It is possible to specify None in case one would like to allow for
            an arbitrary offset to be optimized for the offset_free = 1 case.
        verbose (bool): verbosity.
        nsamples (int): Number of points for the lightcurve sampling.
            If None, the lightcurve will be sampled at the observed data
            points.
        output (bool): If true, will return the model flux values and the offsets.

        >>> self.Plot([10.,7200.,PIBYTWO,300e3,1.0,0.9,0.08,4000.,5000.])
        """
        # Calculate the orbital phases at which the flux will be evaluated
        phases = np.resize(np.linspace(0.,1.,nphases), (self.ndataset, nphases))
        # Fit the data in order to get the offset
        chi2, extras = self.Calc_chi2(par, offset_free=offset_free, DM_AV=DM_AV, verbose=verbose, nsamples=nsamples, full_output=True)
        offset = extras['offset']
        par = extras['par']
        # Calculate the theoretical flux at the orbital phases.
        pred_flux = self.Get_flux_theoretical(par, phases)
        # Calculating the min and the max
        tmp = []
        for i in np.arange(self.ndataset):
            tmp = np.r_[tmp, pred_flux[i]+offset[i]]
        minmag = tmp.min()
        maxmag = tmp.max()
        deltamag = (maxmag - minmag)
        spacing = 0.2

        #---------------------------------
        ##### Plot using matplotlib
        try:
            fig = pylab.gcf()
            try:
                ax = pylab.gca()
            except:
                ax = fig.add_subplot(1,1,1)
        except:
            fig, ax = pylab.subplots(nrows=1, ncols=1)
        ncolors = self.ndataset - 1
        if ncolors == 0:
            ncolors = 1
        for i in np.arange(self.ndataset):
            color = np.ones((self.data['mag'][i].size,1), dtype=float) * matplotlib.cm.jet(float(i)/ncolors)
            ax.errorbar(self.data['phase'][i], self.data['mag'][i], yerr=self.data['err'][i], fmt='none', ecolor=color[0])
            ax.scatter(self.data['phase'][i], self.data['mag'][i], edgecolor=color, facecolor=color)
            ax.plot(phases[i], pred_flux[i], 'k--')
            ax.plot(phases[i], pred_flux[i]+offset[i], 'k-')
            ax.text(1.01, pred_flux[i].max(), self.data['id'][i])
        ax.set_xlim([0,1])
        ax.set_ylim([maxmag+spacing*deltamag, minmag-spacing*deltamag])
        ax.set_xlabel( "Orbital Phase" )
        ax.set_ylabel( "Magnitude" )
        pylab.draw()

        if output:
            return pred_flux, offset
        return

    def Plot_theoretical(self, par, nphases=31, verbose=False, output=False):
        """
        Plots the predicted light curves.

        par (list/array): Parameter list as expected by the Make_surface function.
        nphases (31): Orbital phase resolution of the model
            light curve.
        verbose (False): verbosity.
        output (False): If true, will return the model flux values and the offsets.

        >>> self.Plot_theoretical([PIBYTWO,1.,0.9,4000.,0.08,300e3,5000.,10.,0.])
        """
        # Calculate the orbital phases at which the flux will be evaluated
        phases = np.resize(np.linspace(0.,1.,nphases), (self.ndataset, nphases))
        # Calculate the theoretical flux at the orbital phases.
        pred_flux = self.Get_flux_theoretical(par, phases, func_par=func_par, verbose=verbose)

        #---------------------------------
        ##### Plot using matplotlib
        try:
            fig = pylab.gcf()
            try:
                ax = pylab.gca()
            except:
                ax = fig.add_subplot(1,1,1)
        except:
            fig, ax = pylab.subplots(nrows=1, ncols=1)
        ncolors = self.ndataset - 1
        if ncolors == 0:
            ncolors = 1
        for i in np.arange(self.ndataset):
            color = np.ones((self.data['mag'][i].size,1), dtype=float) * matplotlib.cm.jet(float(i)/ncolors)
            ax.plot(phases[i], pred_flux[i], color=color)
        if output:
            return pred_flux
        return

    def Pretty_print(self, par, make_surface=True, DM=0., AV=0., verbose=True):
        """
        Return a nice representation of the important
        parameters.

        par (list/array): Parameter list as expected by the Make_surface function.
        make_surface (True): Whether to recalculate the 
            surface of the star or not.
        DM (float): Distance modulus o apply to the data.
        AV (float): V band extinction.
        verbose (True): Output the nice representation
            of the important parameters or just return them
            as a list.

        >>> self.Pretty_print([10.,7200.,PIBYTWO,300e3,1.0,0.9,0.08,4000.,5000.])
        """
        if make_surface:
            self.Make_surface(par)
        q = self.star.q
        porb = self.star.porb
        incl = self.star.incl
        omega = self.star.omega
        filling = self.star.filling
        temp = self.star.temp
        tirr = self.star.tirr
        tempgrav = self.star.tempgrav
        k1 = self.star.k1
        tday = (temp**4 + tirr**4)**0.25
        separation = self.star.separation
        roche = self.star.Roche()
        radius = self.star.Radius()
        M1 = self.star.mass1
        M2 = self.star.mass2
        ## below we transform sigma from W m^-2 K^-4 to erg s^-1 cm^-2 K^-4
        ## below we transform the separation from m to cm
        #Lirr = tirr**4 * (cts.sigma*1e3) * (separation*100)**2 * 4*cts.pi
        #eff = Lirr/self.edot
        ## we convert Lirr in Lsun units
        #Lirr /= 3.839e33
        if verbose:
            print( "##### Pretty Print #####" )
            print( "Mass ratio (M2/M1): %6.3f" %q )
            print( "Orbital period: %6.3f hrs" %(porb/3600) )
            print( "Inclination: %5.3f rad (%6.2f deg)" %(incl,incl*cts.RADTODEG) )
            print( "" )
            print( "K1: %7.3f km/s" %(K/1000) )
            print( "" )
            print( "Corotation factor: %4.2f" %omega )
            print( "Filling factor: %6.4f" %filling )
            print( "Gravity Darkening: %5.3f" %tempgrav )
            print( "" )
            print( "Base temperature: %7.2f K" %temp )
            print( "Dayside temperature: %7.2f K" %tday )
            print( "" )
            print( "Distance Modulus: %6.3f" %DM )
            print( "Absorption (V band): %6.3f" %A_V )
            print( "" )
            print( "Orbital separation: %5.4e km" %(separation/1000) )
            print( "Roche lobe size: %6.4f (orb. sep.)" %roche )
            print( "Volume-averaged radius: %6.4f (orb. sep.)" %radius )
            print( "" )
            print( "Mass 1 (modelled star): %5.3f Msun" %M1 )
            print( "Mass 2 (companion star): %5.3f Msun" %M2 )
        return

    def _Read_atmo(self, atmo_fln):
        """_Read_atmo(atmo_fln)
        Reads the atmosphere model data.

        atmo_fln (str): A file containing the grid model information for each
            data set. The format of each line of the file is as follows:
                Col 0: band name
                Col 1: band filename

        >>> self._Read_atmo(atmo_fln)
        """
        f = open(atmo_fln,'r')
        lines = f.readlines()
        self.atmo_grid = []
        for line in lines:
            if (line[0] != '#') and (line[0] != '\n'):
                tmp = line.split()
                self.atmo_grid.append(Atmosphere.AtmoGridPhot.ReadHDF5(tmp[1]))
        return

    def _Read_data(self, data_fln):
        """_Read_data(data_fln)
        Reads the photometric data.

        data_fln (str): A file containing the information for each data set.
            Three formats are currently supported.
            9-column (preferred):
                Col 0: band name
                Col 1: column id for orbital phase. Orbital phases must be 0-1.
                    Phase 0 is defined as the primary star (the one modelled),
                    located at inferior conjunction.
                Col 2: column id for flux/magnitude
                Col 3: column id for flux/magnitude error
                Col 4: shift to phase zero. Sometimes people use other
                    definition for orbital phases, so this allows to correct for
                    it.
                Col 5: band calibration error, in magnitude
                Col 6: softening parameter for asinh magnitude conversion. If
                    the value is 0., then standard magnitudes are used.
                Col 7: flux or mag flag. Currently, all the data must be in the
                    same format.
                    'mag' means magnitude system
                    'flux' means flux system
                Col 8: filename
            8-column (support for asinh magnitudes, no fluxes input):
                Col 0: band name
                Col 1: column id for orbital phase. Orbital phases must be 0-1.
                    Phase 0 is defined as the primary star (the one modelled),
                    located at inferior conjunction.
                Col 2: column id for magnitude
                Col 3: column id for magnitude error
                Col 4: shift to phase zero. Sometimes people use other
                    definition for orbital phases, so this allows to correct for
                    it.
                Col 5: band calibration error, in magnitude
                Col 6: softening parameter for asinh magnitude conversion. If
                    the value is 0., then standard magnitudes are used.
                Col 7: filename
            7-column (only support standard magnitude input):
                Col 0: band name
                Col 1: column id for orbital phase. Orbital phases must be 0-1.
                    Phase 0 is defined as the primary star (the one modelled),
                    located at inferior conjunction.
                Col 2: column id for magnitude
                Col 3: column id for magnitude error
                Col 4: shift to phase zero. Sometimes people use other
                    definition for orbital phases, so this allows to correct for
                    it.
                Col 5: band calibration error, in magnitude
                Col 6: filename

        >>> self._Read_data(data_fln)
        """
        f = open(data_fln,'r')
        lines = f.readlines()
        self.data = {'mag':[], 'phase':[], 'err':[], 'calib':[], 'fln':[], 'id':[], 'softening':[]}
        for line in lines:
            if (line[0] != '#') and (line[0] != '\n'):
                tmp = line.split()
                ## Old version of the data files
                if len(tmp) == 7:
                    d = np.loadtxt(tmp[-1], usecols=[int(tmp[1]),int(tmp[2]),int(tmp[3])], unpack=True)
                    ## With the flag '_' in the observation id, we do not take %1 so that
                    ## we preserve the long-term phase coherence.
                    if tmp[0].find('_') != -1:
                        self.data['phase'].append( np.atleast_1d(d[0] - float(tmp[4])) )
                    else:
                        self.data['phase'].append( np.atleast_1d((d[0] - float(tmp[4]))%1.) )
                    self.data['mag'].append( np.atleast_1d(d[1]) )
                    self.data['err'].append( np.atleast_1d(d[2]) )
                    self.data['calib'].append( float(tmp[5]) )
                    self.data['fln'].append( tmp[-1] )
                    self.data['id'].append( tmp[0] )
                    self.data['softening'].append( 0. )
                ## Old version of the data files including asinh magnitudes
                elif len(tmp) == 8:
                    d = np.loadtxt(tmp[-1], usecols=[int(tmp[1]),int(tmp[2]),int(tmp[3])], unpack=True)
                    # With the flag '_' in the observation id, we do not take %1 so that
                    # we preserve the long-term phase coherence.
                    if tmp[0].find('_') != -1:
                        self.data['phase'].append( np.atleast_1d(d[0] - float(tmp[4])) )
                    else:
                        self.data['phase'].append( np.atleast_1d((d[0] - float(tmp[4]))%1.) )
                    self.data['mag'].append( np.atleast_1d(d[1]) )
                    self.data['err'].append( np.atleast_1d(d[2]) )
                    self.data['calib'].append( float(tmp[5]) )
                    self.data['fln'].append( tmp[-1] )
                    self.data['id'].append( tmp[0] )
                    self.data['softening'].append( float(tmp[6]) )
                ## Current version of the data files including asinh magnitudes
                elif len(tmp) == 9:
                    d = np.loadtxt(tmp[-1], usecols=[int(tmp[1]),int(tmp[2]),int(tmp[3])], unpack=True)
                    ## Data can be set in magnitude
                    if tmp[-2] == 'mag':
                        # With the flag '_' in the observation id, we do not take %1 so that
                        # we preserve the long-term phase coherence.
                        if tmp[0].find('_') != -1:
                            self.data['phase'].append( np.atleast_1d(d[0] - float(tmp[4])) )
                        else:
                            self.data['phase'].append( np.atleast_1d((d[0] - float(tmp[4]))%1.) )
                        self.data['mag'].append( np.atleast_1d(d[1]) )
                        self.data['err'].append( np.atleast_1d(d[2]) )
                        self.data['calib'].append( float(tmp[5]) )
                        self.data['fln'].append( tmp[-1] )
                        self.data['id'].append( tmp[0] )
                        self.data['softening'].append( float(tmp[6]) )
                    ## Data can be set in flux
                    elif tmp[-2] == 'flux':
                        # With the flag '_' in the observation id, we do not take %1 so that
                        # we preserve the long-term phase coherence.
                        if tmp[0].find('_') != -1:
                            self.data['phase'].append( np.atleast_1d(d[0] - float(tmp[4])) )
                        else:
                            self.data['phase'].append( np.atleast_1d((d[0] - float(tmp[4]))%1.) )
                        self.data['flux'].append( np.atleast_1d(d[1]) )
                        self.data['flux_err'].append( np.atleast_1d(d[2]) )
                        self.data['calib'].append( float(tmp[5]) )
                        self.data['fln'].append( tmp[-1] )
                        self.data['id'].append( tmp[0] )
                        self.data['softening'].append( float(tmp[6]) )
                ## Current version of the data files including asinh magnitudes
                else:
                    raise Exception("The data file does not have the expected number of columns.")
        return

    def _Setup(self):
        """_Setup()
        Stores some important information in class variables.

        >>> self._Setup()
        """
        # We calculate the constant for the conversion of K to q (observed
        # velocity semi-amplitude to mass ratio, with K in m/s)
        #self.K_to_q = Utils.Binary.Get_K_to_q(self.porb, self.x2sini)
        # Storing values in 1D arrays.
        # The V band extinction will be extracted from the atmosphere_grid class
        ext = []
        self.data['ext'] = []
        # Converting magnitudes <-> fluxes in case this would be needed for upper limits
        if self.data.has_key('mag'):
            has_mag = True
            self.data['flux'] = []
            self.data['flux_err'] = []
        else:
            has_mag = False
            self.data['mag'] = []
            self.data['err'] = []
        # The grouping will define datasets that are in the same band and can be evaluated only once in order to save on computation.
        grouping = np.arange(self.ndataset)
        for i in np.arange(self.ndataset):
            ext.extend(self.data['phase'][i]*0.+self.atmo_grid[i].meta['ext'])
            self.data['ext'].append(self.atmo_grid[i].meta['ext'])
            if self.data['softening'][i] == 0:
                if has_mag:
                    flux,flux_err = Utils.Flux.Mag_to_flux(self.data['mag'][i], mag_err=self.data['err'][i], flux0=self.atmo_grid[i].meta['zp'])
                else:
                    mag,err = Utils.Flux.Flux_to_mag(self.data['flux'][i], mag_err=self.data['flux_err'][i], flux0=self.atmo_grid[i].meta['zp'])
            else:
                flux,flux_err = Utils.Flux.Asinh_to_flux(self.data['mag'][i], mag_err=self.data['err'][i], flux0=self.atmo_grid[i].meta['zp'], softening=self.data['softening'][i])
            self.data['flux'].append( flux )
            self.data['flux_err'].append( flux_err )
            for j in np.arange(i+1):
                if self.data['id'][i] == self.data['id'][j]:
                    grouping[i] = j
                    break
        self.ext = np.asarray(ext)
        self.grouping = np.asarray(grouping)
        self.data['ext'] = np.asarray(self.data['ext'])
        self.data['calib'] = np.asarray(self.data['calib'])
        self.mag = np.hstack(self.data['mag'])
        self.err = np.hstack(self.data['err'])
        self.phase = np.hstack(self.data['phase'])
        self.flux = np.hstack(self.data['flux'])
        self.flux_err = np.hstack(self.data['flux_err'])
        self.ndata = self.flux.size
        return

######################## class Photometry ########################

