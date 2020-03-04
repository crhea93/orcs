#!/usr/bin/python
# *-* coding: utf-8 *-*
# Author: Thomas Martin <thomas.martin.1@ulaval.ca>
# File: fit.py

# Copyright (c) 2010-2018 Thomas Martin <thomas.martin.1@ulaval.ca>
#
# This file is part of ORCS
#
# ORCS is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ORCS is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public
# License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ORCS.  If not, see <http://www.gnu.org/licenses/>.

"""
ORCS (Outils de Réduction de Cubes Spectraux) provides tools to
extract data from ORBS spectral cubes.

This module contains the fitting classes
"""
import os
import time
import warnings
import logging
import numpy as np
import gvar

import orb.utils.spectrum
import orb.utils.log
import orb.utils.io
import orcs.core
from . import utils

from orcs.core import LineMaps, CubeJobServer

#################################################
#### CLASS SpectralCube #########################
#################################################

class SpectralCube(orcs.core.SpectralCube):
    """Extension of :py:class:`orcs.core.SpectralCube`

    Gives access to an HDF5 cube with extended fit functionalities.

    The child class :py:class:`~orcs.process.SpectralCube` may be prefered in
    general for its broader functionality.

    .. seealso:: :py:class:`orb.core.SpectralCube`
    """

    def _get_integrated_spectrum_fit_path(self, region_name):
        """Return the path to an integrated spectrum fit

        :param region_name: Name of the region
        """
        dirname = os.path.dirname(self._data_path_hdr)
        basename = os.path.basename(self._data_path_hdr)
        return (dirname + os.sep + "INTEGRATED"
                + os.sep + basename + "integrated_spectrum_fit_{}.hdf5".format(region_name))

    def _get_integrated_spectrum_path(self, region_name):
        """Return the path to an integrated spectrum

        :param region_name: Name of the region
        """
        dirname = os.path.dirname(self._data_path_hdr)
        basename = os.path.basename(self._data_path_hdr)
        return (dirname + os.sep + "INTEGRATED"
                + os.sep + basename + "integrated_spectrum_{}.hdf5".format(region_name))

    def fit_integrated_spectra(self, regions_file_path, lines,
                               fmodel='sinc',
                               nofilter=True,
                               subtract_spectrum=None,
                               plot=True,
                               verbose=True,
                               snr_guess=None,
                               max_iter=None,
                               **kwargs):
        """
        Fit integrated spectra and their emission lines parameters.

        :param regions_file_path: Path to a ds9 reg file giving the
          positions of the regions. Each region is considered as a
          different region.

        :param subtract: Spectrum to subtract (must be a spline)

        :param plot: (Optional) If True, plot each intergrated spectrum along
          with the its fit (default True).

        :param verbose: (Optional) If True print the fit results
          (default True).

        :param snr_guess: Guess on the SNR of the spectrum. Can only
          be None or 'auto'. Set it to 'auto' to make a Bayesian
          fit. In this case two fits are made - one with a predefined
          SNR and the other with the SNR deduced from the first
          fit. If None a classical fit is made. (default None).

        :param max_iter: (Optional) Maximum number of iterations
          (default None)
        """
        def _fit_lines(spectrum_bundle, inputparams, kwargs,
                       snr_guess, max_iter, debug):
            import orb.fft
            #_fit = utils.fit_lines_in_spectrum(
            #    params, inputparams, fit_tol,
            #    spectrum, theta_orig,
            #    snr_guess=snr_guess, max_iter=max_iter, debug=debug)
            #if _fit != []: return _fit.convert()
            #else: return _fit
            spectrum = orb.fft.RealSpectrum(spectrum_bundle)
            fit = spectrum.prepared_fit(inputparams, snr_guess=snr_guess,
                                        max_iter=max_iter, **kwargs)
            return fit


        if verbose:
            logging.info("Extracting integrated spectra")

        # Create parameters file
        paramsfile = list()

        # extract and fit regions
        integ_spectra = list()

        regions = self.get_mask_from_ds9_region_file(
            regions_file_path, integrate=False)

        preparation_spectrum = self.get_spectrum(self.dimx/2, self.dimy/2, 3)
        inputparams, kwargs = preparation_spectrum.prepare_fit(
            lines, fmodel=fmodel, nofilter=nofilter, **kwargs)
        
        cjs = CubeJobServer(self)
        all_fit = cjs.process_by_region(
            _fit_lines, regions, subtract_spectrum,
            args=(inputparams, kwargs,
                  snr_guess, max_iter, self.debug),
            modules=())

        lines = inputparams['allparams']['pos_guess_mean']

        # process results
        for iregion in range(len(regions)):
            ifit, ispectrum = all_fit[iregion]

            if ifit != []:

                all_fit_results = list()
                logging.info('Velocity of the first line (km/s): {}'.format(ifit['velocity_gvar'][0]))
                line_names = list()
                for iline in range(np.size(lines)):
                    line_name = orb.core.Lines().round_nm2ang(
                        orb.utils.spectrum.cm12nm(
                            lines[iline]))

                    fit_params = ifit['lines_params']
                    err_params = ifit['lines_params_err']

                    fit_results = {
                        'reg_index': iregion,
                        'line_name': line_name,
                        'h': fit_params[iline, 0],
                        'a': fit_params[iline, 1],
                        'x': fit_params[iline, 2],
                        'v': ifit['velocity'][iline],
                        'fwhm': fit_params[iline, 3],
                        'sigma': fit_params[iline, 4],
                        'broadening': ifit['broadening'][iline],
                        'flux': ifit['flux'][iline],
                        'h_err': err_params[iline, 0],
                        'a_err': err_params[iline, 1],
                        'x_err': err_params[iline, 2],
                        'v_err': ifit['velocity_err'][iline],
                        'broadening_err': ifit['broadening_err'][iline],
                        'fwhm_err': err_params[iline, 3],
                        'sigma_err': err_params[iline, 4],
                        'flux_err': ifit['flux_err'][iline]}
                    all_fit_results.append(fit_results)


                fitted_vector = ifit['fitted_vector']
                fitted_models = ifit['fitted_models']
            else:
                all_fit_results = [dict() for _ in range(len(lines))]
                fitted_vector = np.zeros_like(ispectrum)
                fitted_models = list()

            linesmodel = 'Cm1LinesModel'

            ispectrum.writeto(self._get_integrated_spectrum_path(iregion))
            if isinstance(ifit, orb.fit.OutputParams):
                ifit.save(self._get_integrated_spectrum_fit_path(iregion))

            for fit_results in all_fit_results:
                paramsfile.append(fit_results)
                if verbose:
                    logging.info(
                        '================ Line: {} ============='.format(
                            fit_results['line_name']))
                    for ikey in fit_results:
                        logging.info('{}: {}'.format(
                            ikey, fit_results[ikey]))

            if plot and ifit != []:

                import pylab as pl
                ax1 = pl.subplot(211)
                ax1.plot(axis, ispectrum, c= '0.3',
                         ls='--', lw=1.5,
                         label='orig spectrum')

                for imod in range(len(fitted_models[linesmodel])):
                    ax1.plot(
                        axis,
                        fitted_models[linesmodel][imod]
                        + fitted_models['ContinuumModel'],
                        c= '0.5', ls='-', lw=1.5)

                ax1.plot(axis, fitted_vector, c= '0.',
                         ls='-', lw=1.5,
                         label='fit')
                ax1.grid()
                ax1.legend()
                ax2 = pl.subplot(212, sharex=ax1)
                ax2.plot(axis, ispectrum - fitted_vector, c= 'red',
                         ls='-', lw=1.5, label='residual')
                ax2.grid()
                ax2.legend()
                pl.show()

            integ_spectra.append(ispectrum)

        return paramsfile


    def _fit_wrapper(self, f, args, kwargs):
        lines = args[-1]
        
        subtract_spectrum = None
        if 'subtract_spectrum' in kwargs:
            subtract_spectrum = kwargs.pop('subtract_spectrum')

        mean_flux = False
        if 'mean_flux' in kwargs:
            mean_flux = kwargs.pop('mean_flux')

        spectrum = f(*args[:-1], mean_flux=mean_flux)

        if subtract_spectrum is not None:
            if isinstance(subtract_spectrum, np.ndarray):
                if subtract_spectrum.shape == spectrum.shape:
                    spectrum.data -= subtract_spectrum
                else:
                    raise TypeError('subtract_spectrum must have shape: {}'.format(spectrum.shape))
            else:
                raise TypeError('subtract_spectrum must be a np.ndarray or an orb.core.Cm1Vector1d instance')


        fit_res = spectrum.fit(lines, **kwargs)
        return spectrum.axis.data, spectrum.data, fit_res
    
    
    def fit_lines_in_spectrum(self, *args, **kwargs):
        """Fit lines of a spectrum extracted from a circular region of a
        given radius.

        :param x: X position of the center

        :param y: Y position of the center

        :param r: Radius. If 0, only the central pixel is extracted.

        :param lines: Emission lines to fit (must be in cm-1 if the
          cube is in wavenumber. must be in nm otherwise).

        :param nofilter: (Optional) If True, Filter model is not added
          and the fit is made with a single range set to the filter
          bandpass.

        :param subtract_spectrum: (Optional) Remove the given spectrum
          from the extracted spectrum before fitting
          parameters. Useful to remove sky spectrum. Both spectra must
          have the same size.

        :param snr_guess: Guess on the SNR of the spectrum. Necessary
          to make a Bayesian fit (If unknown you can set it to 'auto'
          to try an automatic mode, two fits are made - one with a
          predefined SNR and the other with the SNR deduced from the
          first fit). If None a classical fit is made.

        :param max_iter: (Optional) Maximum number of iterations
          (default None)

        :param mean_flux: (Optional) If True the flux of the spectrum
          is the mean flux of the extracted region (default False).

        :param kwargs: Keyword arguments of the function
          :py:meth:`~SpectralCube._fit_lines_in_spectrum`.

        :returns: a tuple (axis, spectrum, fit_dict). fit_dict is a
          dictionary containing the fit results (same output as
          :py:meth:`orb.fit.fit_lines_in_spectrum`)
        """
        return self._fit_wrapper(self.get_spectrum, args, kwargs)

    def fit_lines_in_spectrum_bin(self, *args, **kwargs):
        """Fit lines of a spectrum extracted from a squared region of a
        given size.

        :param x: X position of the bottom-left pixel

        :param y: Y position of the bottom-left pixel

        :param b: Binning. If 0, only the central pixel is extracted.

        :param lines: Emission lines to fit (must be in cm-1 if the
          cube is in wavenumber. must be in nm otherwise).

        :param nofilter: (Optional) If True, Filter model is not added
          and the fit is made with a single range set to the filter
          bandpass.

        :param subtract_spectrum: (Optional) Remove the given spectrum
          from the extracted spectrum before fitting
          parameters. Useful to remove sky spectrum. Both spectra must
          have the same size.

        :param snr_guess: Guess on the SNR of the spectrum. Necessary
          to make a Bayesian fit (If unknown you can set it to 'auto'
          to try an automatic mode, two fits are made - one with a
          predefined SNR and the other with the SNR deduced from the
          first fit). If None a classical fit is made.

        :param max_iter: (Optional) Maximum number of iterations
          (default None)

        :param mean_flux: (Optional) If True the flux of the spectrum
          is the mean flux of the extracted region (default False).

        :param kwargs: Keyword arguments of the function
          :py:meth:`orb.fit.fit_lines_in_spectrum`.

        :returns: a tuple (axis, spectrum, fit_dict). fit_dict is a
          dictionary containing the fit results (same output as
          :py:meth:`orb.fit.fit_lines_in_spectrum`)
        """
        return self._fit_wrapper(self.get_spectrum_bin, args, kwargs)

    def fit_lines_in_integrated_region(self, *args, **kwargs):
        """Fit lines of a spectrum integrated over a given region (can
        be a list of pixels as returned by the function
        :py:meth:`numpy.nonzero` or a ds9 region file).

        :param region: Region to integrate (can be a list of pixel
          coordinates as returned by the function
          :py:meth:`numpy.nonzero` or the path to a ds9 region
          file). If it is a ds9 region file, multiple regions can be
          defined and all will be integrated into one spectrum.

        :param lines: Emission lines to fit (must be in cm-1 if the
          cube is in wavenumber. must be in nm otherwise).

        :param nofilter: (Optional) If True, Filter model is not added
          and the fit is made with a single range set to the filter
          bandpass.

        :param subtract_spectrum: (Optional) Remove the given spectrum
          from the extracted spectrum before fitting
          parameters. Useful to remove sky spectrum. Both spectra must
          have the same size.

        :param snr_guess: Guess on the SNR of the spectrum. Necessary
          to make a Bayesian fit (If unknown you can set it to 'auto'
          to try an automatic mode, two fits are made - one with a
          predefined SNR and the other with the SNR deduced from the
          first fit). If None a classical fit is made.

        :param max_iter: (Optional) Maximum number of iterations
          (default None)

        :param mean_flux: (Optional) If True the flux of the spectrum
          is the mean flux of the extracted region (default False).

        :param kwargs: Keyword arguments of the function
          :py:meth:`~SpectralCube._fit_lines_in_spectrum`.

        :returns: a tuple (axis, spectrum, fit_dict). fit_dict is a
          dictionary containing the fit results (same output as
          :py:meth:`~SpectralCube._fit_lines_in_spectrum`)
        """
        return self._fit_wrapper(self.get_spectrum_from_region, args, kwargs)

    def fit_lines_in_region(self, region, lines, fmodel='sinc', binning=1, nofilter=False,
                            subtract_spectrum=None, snr_guess=None, max_iter=None,
                            timeout=None, **kwargs):
        """Fit lines in a given region of the cube. All the pixels in
        the defined region are fitted one by one and a set of maps
        containing the fitted paramaters are written. Note that the
        pixels can be binned.

        :param lines: Emission lines to fit (must be in cm-1 if the
          cube is in wavenumber. must be in nm otherwise).

        :param region: Region to fit. Multiple regions can be used to
          define the fitted region. They do not need to be contiguous.

        :param nofilter: (Optional) If True, Filter model is not added
          and the fit is made with a single range set to the filter
          bandpass.

        :param subtract_spectrum: (Optional) Remove the given spectrum
          from the extracted spectrum before fitting
          parameters. Useful to remove sky spectrum. Both spectra must
          have the same size.

        :param snr_guess: Guess on the SNR of the spectrum. Can only
          be None or 'auto'. Set it to 'auto' to make a Bayesian
          fit. In this case two fits are made - one with a predefined
          SNR and the other with the SNR deduced from the first
          fit. If None a classical fit is made.

        :param max_iter: (Optional) Maximum number of iterations
          (default None)

        :timeout: (Optional) max processing time per pixel. If reached, the given
          pixel is passed (default None).

        :param kwargs: Keyword arguments of the function
          :py:meth:`~SpectralCube._fit_lines_in_spectrum`.

        .. note:: You can pass the fitting parameters (e.g. pos_cov,
          sigma_cov etc.) as maps (a 2d numy.ndarray instance or a
          path to a map). But you have to append the suffix '_map' to
          the parameter you want to map. Any nan or inf in the map
          will be replaced by the median of the map. This mode can be
          used to map parameters at a given binning from the result of
          the fit made at a higher binning.
        """
        def fit_lines_in_pixel(spectrum, spectrum_bundle, inputparams, 
                               theta_map_ij, snr_guess, sky_vel_ij, calib_coeff_ij,
                               flux_sdev_ij, debug, max_iter, subtract_spectrum,
                               binning, mapped_kwargs):

            import orb.utils.spectrum
            import orb.fft
            
            stime = time.time()
            if debug:
                import orb.utils.log
                orb.utils.log.setup_socket_logging()
            else:
                warnings.simplefilter('ignore', RuntimeWarning)


            # correct spectrum for nans
            spectrum[np.isnan(spectrum)] = 0.

            spectrum_bundle['data'] = spectrum
            spectrum_bundle['err'] = np.ones(spectrum.size, dtype=float) * flux_sdev_ij
            
            spectrum = orb.fft.RealSpectrum(spectrum_bundle)
            spectrum.params['calib_coeff_orig'] = orb.utils.spectrum.corr2theta(theta_map_ij)

            # correct spectrum for sky velocity

            if not np.isclose(calib_coeff_ij - spectrum.params['calib_coeff'], 0):
                raise NotImplementedError()

                # logging.debug('spectrum is interpolated to correct for wavelength calibration change: {} km/s'.format(sky_vel_ij))
                ## here spectrum must be projected onto the base axis
                
            # subtract spectrum
            if subtract_spectrum is not None:
                subtract_spectrum[np.isnan(subtract_spectrum)] == 0.
                spectrum.data -= subtract_spectrum * binning ** 2.

            # add flux uncertainty to the spectrum
            if debug:
                logging.debug('passed mapped kwargs: {}'.format(mapped_kwargs))

            fmapped_kwargs = dict()
            while len(mapped_kwargs) > 0:
                if debug:
                    logging.debug('{}'.format(mapped_kwargs))
                for key in list(mapped_kwargs.keys()):
                    rkey = key[:-len(key.split('_')[-1])-1]
                    index = int(key.split('_')[-1])
                    if rkey not in fmapped_kwargs:
                        if index == 0:
                            fmapped_kwargs[rkey] = list([mapped_kwargs.pop(key)])
                    elif index == len(fmapped_kwargs[rkey]):
                        newentry = fmapped_kwargs[rkey]
                        newentry.append(mapped_kwargs.pop(key))
                        fmapped_kwargs[rkey] = newentry
            mapped_kwargs = fmapped_kwargs

            if debug:
                logging.debug('transformed mapped kwargs: {}'.format(mapped_kwargs))

            try:
                ifit = spectrum.prepared_fit(
                    inputparams, snr_guess=snr_guess, max_iter=max_iter,
                    **mapped_kwargs)

            except Exception as e:
                if debug:
                    logging.debug('Exception occured during fit: {}'.format(e))
                ifit = []

            if ifit != []:
                if debug:
                    logging.debug('pure fit time: {} s'.format(ifit['fit_time']))
                    logging.debug('fit function time: {} s'.format(time.time() - stime))
                    logging.debug('velocity: {}'.format(ifit['velocity_gvar']))
                    logging.debug('broadening: {}'.format(ifit['broadening_gvar']))

                return {
                    'height': ifit['lines_params'][:,0],
                    'amplitude': ifit['lines_params'][:,1],
                    'fwhm': ifit['lines_params'][:,3],
                    'velocity': ifit['velocity'],
                    'sigma': ifit['broadening'],
                    'flux': ifit['flux'],
                    'height-err': ifit['lines_params_err'][:,0],
                    'amplitude-err': ifit['lines_params_err'][:,1],
                    'fwhm-err': ifit['lines_params_err'][:,3],
                    'velocity-err': ifit['velocity_err'],
                    'sigma-err': ifit['broadening_err'],
                    'flux-err': ifit['flux_err'],
                    'chi2': ifit['chi2'],
                    'rchi2': ifit['rchi2'],
                    'logGBF': ifit['logGBF'],
                    'ks_pvalue': ifit['ks_pvalue']}

            else:
                return {
                    'height': None,
                    'amplitude': None,
                    'fwhm': None,
                    'velocity': None,
                    'sigma': None,
                    'flux': None,
                    'height-err': None,
                    'amplitude-err': None,
                    'fwhm-err': None,
                    'velocity-err': None,
                    'sigma-err': None,
                    'flux-err': None,
                    'chi2': None,
                    'rchi2': None,
                    'logGBF': None,
                    'ks_pvalue': None}

        region = self.get_mask_from_ds9_region_file(region)

        # check maps in params
        mapped_kwargs = dict()
        for key in list(kwargs.keys()):
            if '_map' in key:
                rkey = key[:-len('_map')]
                if rkey in list(kwargs.keys()):
                    raise KeyError('a mapped value has already been defined with {}. Please remove {}.'.format(key, rkey))
                vmaps = kwargs.pop(key)
                if not isinstance(vmaps, tuple) and not isinstance(vmaps, list):
                    vmaps = list([vmaps])

                for i in range(len(vmaps)):
                    ivmap = vmaps[i]
                    if isinstance(ivmap, str):
                        ivmap = orb.utils.io.read_fits(ivmap)
                    elif not isinstance(ivmap, np.ndarray):
                        raise TypeError('parameter map {} must be a path to a fits file or a numpy.ndarray instance'.format(key))
                    if ivmap.ndim != 2:
                        raise TypeError('parameter map {} must have exactly two dimensions'.format(key))
                    if ivmap.shape != (self.dimx, self.dimy):
                        # try to detect binning
                        _bin = orb.utils.image.compute_binning(ivmap.shape, (self.dimx, self.dimy))
                        if _bin[0] == _bin[1]:
                            if debug:
                                logging.debug('parameter map binned {}x{}'.format(_bin[0], _bin[1]))
                            ivmap = orb.cutils.unbin_image(ivmap, self.dimx, self.dimy)
                        else:
                            if debug:
                                logging.debug('parameter map not binned. Interpolating {} map from {} to ({}, {})'.format(key, ivmap.shape, self.dimx, self.dimy))
                            ivmap = orb.utils.image.interpolate_map(ivmap, self.dimx, self.dimy)
                        if debug:
                            logging.debug('final {} map shape: {}'.format(rkey, ivmap.shape))

                    kwargs[rkey] = np.nanmedian(ivmap)
                    if debug:
                        logging.debug('final {} map median: {}'.format(rkey, kwargs[rkey]))
                    if np.any(np.isnan(ivmap)) or np.any(np.isinf(ivmap)):
                        logging.warning('nans and infs in passed map {} will be replaced by the median of the map'.format(key))
                    ivmap[np.isnan(ivmap)] = kwargs[rkey]
                    ivmap[np.isinf(ivmap)] = kwargs[rkey]
                    mapped_kwargs[rkey + '_{}'.format(i)] = ivmap


        if snr_guess not in ('auto', None):
            raise ValueError("snr_guess must be 'auto' or None")


        ## init LineMaps object
        linemaps = LineMaps(
            self.dimx, self.dimy,
            orb.core.Lines().get_line_cm1(lines),
            self.params.wavenumber,
            binning, self.config.DIV_NB,
            wcs_header=self.get_wcs_header(),
            instrument=self.instrument,
            data_prefix=self._data_prefix,
            config=self.config)

        # check subtract spectrum
        if subtract_spectrum is not None:
            if not callable(subtract_spectrum):
                orb.utils.validate.is_1darray(subtract_spectrum, object_name='subtract_spectrum')
                if np.all(subtract_spectrum == 0.): subtract_spectrum = None
            

        mask = np.zeros((self.dimx, self.dimy), dtype=bool)
        mask[region] = True

        theta_map = orb.utils.image.nanbin_image(self.get_theta_map(), binning)

        mask = np.zeros((self.dimx, self.dimy), dtype=float)
        mask[region] = 1

        mask_bin = orb.utils.image.nanbin_image(mask, binning)

        total_fit_nb = np.nansum(mask_bin)
        logging.info('Number of spectra to fit: {}'.format(int(total_fit_nb)))

        if self.get_sky_velocity_map() is not None:
            sky_velocity_map = orb.utils.image.nanbin_image(
                self.get_sky_velocity_map(), binning)
        else:
            sky_velocity_map = orb.utils.image.nanbin_image(
                np.zeros((self.dimx, self.dimy), dtype=float), binning)

        calibration_coeff_map = orb.utils.image.nanbin_image(
            self.get_calibration_coeff_map(), binning)

        flux_uncertainty = self.get_flux_uncertainty()
        if flux_uncertainty is not None:
            flux_uncertainty = orb.utils.image.nanbin_image(flux_uncertainty, binning)
        else:
            flux_uncertainty = orb.utils.image.nanbin_image(
                np.ones((self.dimx, self.dimy), dtype=float), binning) * binning**2.

        preparation_spectrum = self.get_spectrum(self.dimx/2, self.dimy/2, 3)
        inputparams, kwargs = preparation_spectrum.prepare_fit(
            lines, fmodel=fmodel, nofilter=nofilter, **kwargs)
        spectrum_bundle = preparation_spectrum.to_bundle()

        cjs = orcs.core.CubeJobServer(self)
        out = cjs.process_by_pixel(fit_lines_in_pixel,
                                   args=[spectrum_bundle, inputparams,
                                         theta_map, snr_guess, sky_velocity_map,
                                         calibration_coeff_map,
                                         flux_uncertainty, self.debug, max_iter,
                                         subtract_spectrum, binning],
                                   kwargs=mapped_kwargs,
                                   modules=['numpy as np', 'gvar', 'orcs.utils',
                                            'logging', 'warnings', 'time',
                                            'import orb.utils.spectrum',
                                            'import orb.utils.vector'],
                                   mask=mask,
                                   binning=binning,
                                   timeout=timeout)

        for key in out:
            linemaps.set_map(key, out[key],
                             x_range=[0, self.dimx],
                             y_range=[0, self.dimy])


        linemaps.write_maps()

                    
    def get_amp_ratio_from_flux_ratio(self, line0, line1, flux_ratio):
        """Return the amplitude ratio (amp(line0) / amp(line1)) to define from the flux ratio
        (at constant fwhm and broadening).

        :param line0: Wavenumber of the line 0 (in cm-1).

        :param line1: Wavenumber of the line 1 (in cm-1).

        :param flux_ratio: Flux ratio: flux(line0) / flux(line1).
        """
        if isinstance(line0, str):
            line0 = orb.core.Lines().get_line_cm1(line0)
        if isinstance(line1, str):
            line1 = orb.core.Lines().get_line_cm1(line1)
        return orb.utils.spectrum.amp_ratio_from_flux_ratio(line0, line1, flux_ratio)
