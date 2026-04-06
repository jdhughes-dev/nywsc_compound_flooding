import itertools

import flopy
import geopandas as gpd
import pandas as pd
import pyswmm

from liss_settings import get_modflow_grid_name


def intersect_points_grid(
    domain="gp",
    boundary_condition="chd",
    sim_ws=None,
    swmm_pth=None,
    pts_pth=None,
    pts_name_col="Name",
    grid_poly=None,
    n_junctions=1000,
    crs="epsg:4456",
):
    """
    Intersects specified points with a grid polygon and retrieves information about junctions.

    This function reads point data from a specified shapefile, samples a given number of junctions,
    and intersects these junctions with a provided grid polygon. It then retrieves the corresponding
    SWMM node information, including invert elevations, and returns the number of junctions sampled,
    a dictionary of cell IDs, a dictionary of SWMM nodes, and a dictionary of invert elevations in feet.

    Parameters:
    ----------
    domain : str
        Model domain name. Greenport (gp) or Port Jefferson (PJ). Default is gp.
    boundary_condition
    sim_ws : str
        The workspace directory containing the MODFLOW 6 simulation files. If None, the function will
        attempt to load from the current working directory.
    swmm_pth : str
        The file path to the SWMM input file. If None, a default path is used.
    pts_pth : str
        The file path to the shapefile containing point data. If None, a default path is used.
    grid_poly : GeoDataFrame
        A GeoDataFrame representing the grid polygon to intersect with the points.
    n_junctions : int
        The desired number of junctions to sample from the point data. Default is 12.
    crs : str, optional
        The coordinate reference system (CRS) to assign to the GeoDataFrame. Default is 'epsg:4456'.

    Returns:
    -------
    tuple
        A tuple containing:
        - n_junctions (int): The number of junctions actually sampled.
        - junctions (list): List of selected junction names.
        - mf6_cells (dict): A dictionary mapping junction names to their corresponding cell IDs.
        - swmm_inverts (dict): A dictionary mapping junction names to their invert elevations in feet.
    """
    domain = domain.lower()
    boundary_condition = boundary_condition.lower()
    if domain not in ("gp", "pj"):
        assert False, "domain must be 'gp' or 'pj'"
    if boundary_condition not in ("chd", "ghb"):
        assert False, "boundary condition must be 'chd' or 'ghb'"

    mf_grid_name = get_modflow_grid_name(
        domain=domain,
        boundary_condition=boundary_condition,
        )

    if sim_ws is None:
        sim_ws = f"../modflow/{mf_grid_name}/base"
    if pts_pth is None:
        pts_pth = f"../swmm/{domain}/Manhole_elevations.zip!Manhole_elevations/Manhole_elevation.shp"
    if swmm_pth is None:
        swmm_pth = f"../swmm/{domain}/Sewer_GP_V4.inp"

    mf_sim = flopy.mf6.MFSimulation.load(sim_ws=sim_ws, load_only=[], verbosity_level=0)
    gwf = gwf = mf_sim.get_model("gwf")
    mg = gwf.modelgrid
    grid_poly = mg.geo_dataframe.set_crs(crs)

    grid_poly["cid"] = [
        (r, c) for r, c in itertools.product(range(mg.nrow), range(mg.ncol))
    ]
    # we could update this to be in other layers
    grid_poly["bot01"] = mg.botm[1].ravel()

    # ----------------------------------------------------------------
    bnds = pd.Dataframe()
    bnds["idom"] = mg.idomain[0].flatten()
    bnds["top"] = mg.top.flatten()
    for i, arr in enumerate(mg.botm):
        bnds[f"bot{i + 1:02d}"] = arr.flatten()
    # import the shapefile with x + y provided by VP
    path = "../swmm/PJ/PJ_Sewer_GIS/Junctions.shp"
    junctions_shp = gpd.read_file(path)
    junctions_shp = junctions_shp.to_crs(epsg=4456)
    junctions_shp.to_file("../swmm/PJ/PJ_Sewer_GIS/Juntions_4456.shp")

    with pyswmm.Simulation(str(swmm_pth)) as swmm_sim:
        # some shapefile junctions might not be in SWMM?
        junction_name = [n.nodeid for n in pyswmm.Nodes(swmm_sim)]
        junction_elev = [n.invert_elevation for n in pyswmm.Nodes(swmm_sim)]
        # confirm with the .inp file that this is correct
        junction_df = pd.DataFrame(
            {"Name": junction_name, "elev_navd88": junction_elev}
        )
    junction_df = junctions_shp.merge(junction_df, on="Name")

    # --------------

    pts = gpd.read_file(pts_pth).to_crs(grid_poly.crs)

    # pull in the junctions listed in SWMM
    m_to_ft = 3.28084
    with pyswmm.Simulation(str(swmm_pth)) as swmm_sim:
        # some shapefile junctions might not be in SWMM?
        swmm_junctions = [n.nodeid for n in pyswmm.Nodes(swmm_sim)]
        possible_junctions = pts.loc[pts[pts_name_col].isin(swmm_junctions)].copy()
        possible_junctions["invert_elev_ft"] = [
            n.invert_elevation * m_to_ft
            for n in pyswmm.Nodes(swmm_sim)
            if n.nodeid in possible_junctions["Name"].tolist()
        ]

    if n_junctions > len(possible_junctions):
        print("# of junctions selected greater than # of point features")
        n_junctions = len(possible_junctions)
        print(f"new n_junctions == {n_junctions}")

    selected_junctions = possible_junctions.sample(
        n_junctions, random_state=0
    )  # ['Name'].values

    # slice the pts to grab desired junctions, join with model grid
    mf6_swmm_connect = (
        selected_junctions[["Name", "invert_elev_ft", "geometry"]]
        .sjoin(grid_poly)[["Name", "cid", "bot01", "invert_elev_ft"]]
        .set_index("Name")
    )

    mf6_cells = mf6_swmm_connect["cid"].to_dict()
    # swmm_nodes = mf6_swmm_connect['swmm_node'].to_dict()
    swmm_inverts = mf6_swmm_connect["invert_elev_ft"].to_dict()

    return (
        n_junctions,
        selected_junctions["Name"].tolist(),
        mf6_cells,
        swmm_inverts,
        possible_junctions,
    )


if __name__ == "main":
    intersect_points_grid()
