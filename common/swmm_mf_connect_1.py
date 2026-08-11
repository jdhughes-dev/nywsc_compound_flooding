"""RETAINED FOR THE RETIRED PJ NOTEBOOKS. Do not use in new work.

This is the earlier version of `swmm_mf_connect`, kept only so that

    notebooks-PJ/_RETIRED_step2_run_dflow-modflow_variable_dt_withswmm.ipynb
    notebooks-PJ/_RETIRED_step2_run_dflow-modflow_variable_dt_withswmm1min.ipynb

still open and run. Those two are the only importers left in the repository; the
GP pipeline and every live notebook use `swmm_mf_connect`. Confirm that with

    grep -rl swmm_mf_connect_1 --include=*.ipynb --include=*.py .

before concluding this file is dead and deleting it. It looks unreferenced from
the GP side alone, and it is not.

The two are NOT interchangeable. `intersect_points_grid` here takes
`swmm_pts_pth` and no domain, so it cannot address the per-domain, per-boundary
condition grids; it has no `n_junctions`, `seed` or `junction_names`, so it
cannot reproduce a junction subset; and its fifth return value is a junction
DataFrame where the current one returns the full set of possible junctions.
Anything written against one will not work against the other.

Retire this file when the PJ manuscript is out and its notebooks go, not before.
"""
import itertools
import geopandas as gpd
import pandas as pd
import pyswmm
import flopy

def intersect_points_grid(sim_ws=None, swmm_pth=None, swmm_pts_pth=None, pts_name_col='Name',  crs='epsg:4456'):
    '''
    Intersects specified points with a grid polygon and retrieves information about junctions.

    This function reads point data from a specified shapefile, samples a given number of junctions,
    and intersects these junctions with a provided grid polygon. It then retrieves the corresponding
    SWMM node information, including invert elevations, and returns the number of junctions sampled,
    a dictionary of cell IDs, a dictionary of SWMM nodes, and a dictionary of invert elevations in feet.

    Parameters:
    ----------
    sim_ws : str
        The workspace directory containing the MODFLOW 6 simulation files. If None, the function will
        attempt to load from the current working directory.
    swmm_pth : str
        The file path to the SWMM input file. 
    swmm_pts_pth : str
        The file path to the shapefile containing SWMM point data.

    crs : str, optional
        The coordinate reference system (CRS) to assign to the GeoDataFrame. Default is 'epsg:4456'.

    Returns:
    -------
    tuple
        A tuple containing:
        - junctions (list): List of selected junction names.
        - mf6_cells (dict): A dictionary mapping junction names to their corresponding cell IDs.
        - swmm_inverts (dict): A dictionary mapping junction names to their invert elevations in feet.
    '''


    mf_sim = flopy.mf6.MFSimulation.load(sim_ws=sim_ws, load_only=[], verbosity_level=0)
    gwf = gwf = mf_sim.get_model(mf_sim.model_names[0])
    mg = gwf.modelgrid
    bnds = mg.geo_dataframe.set_crs(crs)
    bnds['row'] = [x[0] for x in itertools.product(range(mg.nrow), range(mg.ncol))]
    bnds['col']=  [x[1] for x in itertools.product(range(mg.nrow), range(mg.ncol))]
    bnds['idom'] = mg.idomain[0].flatten()
    bnds['top'] = mg.top.flatten()
    for i,arr in enumerate(mg.botm):
        bnds[f'bot{i+1:02d}'] = arr.flatten()
    #----------------------------------------------------------------
    junctions_shp =gpd.read_file(swmm_pts_pth)
    junctions_shp=junctions_shp.to_crs(crs)
    junctions_shp.to_file('../swmm/PJ/PJ_Sewer_GIS/Juntions_4456.shp')
    #--------------

    # pull in the junctions listed in SWMM
    m_to_ft = 3.28084

    with pyswmm.Simulation(str(swmm_pth)) as swmm_sim:
        # some shapefile junctions might not be in SWMM? 
        junction_name = [n.nodeid for n in pyswmm.Nodes(swmm_sim)]
        junction_elev = [n.invert_elevation * m_to_ft for n in pyswmm.Nodes(swmm_sim) if n.nodeid in junction_name]
        junction_df = pd.DataFrame({'Name':junction_name, 'invert_elev_ft_navd88':junction_elev})
    junction_df = junctions_shp.merge(junction_df, left_on=pts_name_col,right_on ='Name')
    junction_gdf = gpd.GeoDataFrame(junction_df,geometry= junction_df['geometry'], crs = 'EPSG:4456')
    print('SWMM Junctions/Nodes')
    display(junction_gdf.head())
    junctions_lrc = junction_gdf.sjoin(bnds.copy()).drop('index_right',axis=1)
    divs = ['top'] + [f'bot{i+1:02d}' for i in range(20)]
    for i in range(len(divs)-1):
        ul = divs[i] # upper layer
        ll = divs[i+1] # lower layer 
        junctions_lrc.loc[(junctions_lrc.invert_elev_ft_navd88<junctions_lrc[ul]) &
                    (junctions_lrc.invert_elev_ft_navd88>junctions_lrc[ll]) &
                    (junctions_lrc['idom']>0),'lay'] = int(i)

    # missing = junctions_lrc[junctions_lrc['lay'].isna()]
    # print("Junctions without a valid layer:")
    # display(missing[['Name','invert_elev_ft_navd88','row','col','top'] + [c for c in junctions_lrc.columns if c.startswith('bot')]])
    junctions_lrc['lay'] = junctions_lrc['lay'].fillna(0).astype(int)

    print('SWMM Junctions with l,r,c')
    display(junctions_lrc.head())

    # slice the pts to grab desired junctions, join with model grid
    mf6_swmm_connect = junctions_lrc[['Name', 'geometry', 'invert_elev_ft_navd88', 'lay','row', 'col',]].set_index('Name')
    mf6_swmm_connect['cid'] = [(l,r, c) for l,r,c in zip(junctions_lrc['lay'], junctions_lrc['row'], junctions_lrc['col'])]

    mf6_cells = mf6_swmm_connect['cid'].to_dict()
    # swmm_nodes = mf6_swmm_connect['swmm_node'].to_dict()
    swmm_inverts = mf6_swmm_connect['invert_elev_ft_navd88'].to_dict()
    n_junctions = len(mf6_cells)

    return n_junctions, junctions_lrc['Name'].tolist(), mf6_cells, swmm_inverts, junction_df

if __name__ == 'main':
    intersect_points_grid()
