# AUTOGENERATED! DO NOT EDIT! File to edit: DataPipelineNotebooks/2.ConvertToZarr.ipynb (unless otherwise specified).

__all__ = ['ConvertToZarr']

# Cell
import xarray as xr
import zarr
from joblib import Parallel, delayed
import pandas as pd
import os

# Cell
class ConvertToZarr:
    """
    Class which encapsulates the logic to convert a set of filtered netCDF files to Zarr
    """

    def __init__(self, seasons, regions, data_root, interpolate=1):
        """
        Initialize the class

        Keyword Arguments
        seasons: list of season values to process
        regions: dictonary of Key: State and Value: List of Regions to process for that state
        data_root: the root path of the data folders which contains the 3.GFSFiltered1xInterpolation
        interpolate: the amount of interpolation applied in in the previous ParseGFS notebook (used for finding the correct input/output paths)
        """
        self.processed_path = data_root + '/3.GFSFiltered'+ str(interpolate) + 'xInterpolation/'
        self.zarr_base_path = data_root + '/4.GFSFiltered'+ str(interpolate) + 'xInterpolationZarr/'

        self.seasons = seasons
        self.regions = regions
        self.data_root = data_root

        if not os.path.exists(self.zarr_base_path):
            os.makedirs(self.zarr_base_path)

    def compute_region(self, region_name, season, state):
        """
        Calculates the zarr conversion for a specific region, season and state and indexes it for efficient lookup

        Keyword Arguments
        region_name: name of the region to process
        season: season to process
        state: state to process (region must be a part of the state)
        """
        first = True
        base_path = self.processed_path + season + '/' + '/Region_' + region_name
        zarr_path = self.zarr_base_path + season + '/' + state + '/Region_' + region_name + '.zarr'

        #TODO: refactor these to be shared code as logic also exists in ParseGFS
        p = 181
        if season in ['15-16', '19-20']:
            p = 182 #leap years

        snow_start_date = '2015-11-01'
        if season == '16-17':
            snow_start_date = '2016-11-01'
        if season == '17-18':
            snow_start_date = '2017-11-01'
        if season == '18-19':
            snow_start_date = '2018-11-01'
        if season == '19-20':
            snow_start_date = '2019-11-01'

        date_values_pd = pd.date_range(snow_start_date, periods=p, freq="D")
        try:
            with xr.open_zarr(zarr_path) as z:
                if z.time.values[-1] == date_values_pd[-1]:
                    print(' already exists: ' + region_name + ' ' + season + ' ' + state)
                    z.close()
                    return
                else:
                    #already exists but incomplete
                    date_values_pd = [pd.Timestamp(v) for v in date_values_pd.values.astype('datetime64[ns]') if v not in z.time.values]
                    print(' some exist but have to complete ' + str(len(date_values_pd)))
                    first = False
        except ValueError as err:
            #ignore as it doesn't exist yet
            pass

        #sometimes vars get added, filter to only the list of vars in the first dataset for that region
        #TODO: handle the case where the first dataset has more vars than subsequent ones
        final_vars = None
        for d in date_values_pd:

            path =  base_path + '_' + d.strftime('%Y%m%d') + '.nc'
            print('On ' + str(path.split('/')[-1]))

            try:
                ds = xr.open_dataset(path, chunks={'latitude':1, 'longitude':1})
            except OSError as err:
                print(' missing file: ' + path)
                continue

            ds = ds.to_array(name='vars').chunk({'time':1, 'latitude':1, 'longitude':1, 'variable':-1}).to_dataset()

            try:

                if first:
                    final_vars = list(ds.variable.values)
                    ds.to_zarr(zarr_path, consolidated=True)
                    first=False
                else:
                    assert(final_vars is not None)
                    ds = ds.sel(variable=ds.variable.isin(final_vars))
                    ds.to_zarr(zarr_path, consolidated=True, append_dim='time')
            except ValueError as err:
                print('Value Error ' + format(err) + ' on ' + zarr_path )
                return

    def process_tuple(self, t):
        """
        Entry method to call compute_region with a tuple
        Basically a helper for executing with joblib parallel

        Keyword Arguments
        t: the tuple containing the region, season and state
        """
        self.compute_region(t[0], t[1], t[2])

    def make_list(self):
        """
        Helper method to make the list of values to process
        """
        to_process = []
        for s in self.seasons:
            for state in self.regions.keys():
                for r in self.regions[state]:
                    to_process.append((r,s,state))
        return to_process

    def convert_local(self, jobs=15):
        l = self.make_list()

        #one state & season takes about 6 hours with 15 cores on my machine
        Parallel(n_jobs=jobs, backend="multiprocessing")(map(delayed(self.process_tuple), l))