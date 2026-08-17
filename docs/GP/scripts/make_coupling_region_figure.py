"""The coupling region at all three hydrodynamic resolutions.

Everything drawn here is version-controlled input rather than simulation output --
the three D-Flow FM net files, the MODFLOW~6 coastal boundary shapefile, and the
SWMM network -- so unlike the other figures this one needs no archive and rebuilds
from the repository alone.

The sewer network and the groundwater boundary are drawn identically in all three
panels because they are identical in all three simulations. Only the mesh changes,
which is the point of the figure and of the demonstration it belongs to.
"""
import pathlib as pl
import sys

import geopandas as gpd
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import xugrid
from matplotlib.collections import LineCollection
from shapely.geometry import LineString

import contextily as cx
import flopy.plot.styles as styles

HERE = pl.Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "common"))
# cx_provider is USGS.USTopo, the basemap the rest of the project uses.
from liss_settings import (get_dflow_control_path, get_dflow_grid_name,  # noqa: E402
                           cx_provider)

mpl.rcParams["ps.fonttype"] = 42

OUT = HERE.parent / "figures" / "coupling_region.pdf"
CRS = "EPSG:32618"                       # the CRS the model shapefiles are in
MARGIN = 400.0                           # m of padding around the groundwater model
GRIDS = [("coarse", "Coarse"), ("medium", "Medium"), ("high", "Fine")]

C_MESH = "0.62"
C_BND = "#1f77b4"
C_PIPE = "#8c564b"
C_JUNC = "#d62728"


def _sections(inp, name):
    rows, inside = [], False
    for line in pl.Path(inp).read_text(errors="replace").splitlines():
        s = line.strip()
        if s.startswith("["):
            inside = s.upper().startswith(f"[{name}")
            continue
        if inside and s and not s.startswith(";"):
            rows.append(s.split())
    return rows


def sewer_network():
    """Junction points and conduit lines, in the model CRS.

    Conduit geometry is assembled from the .inp node pairs and the junction
    shapefile rather than read from a line shapefile, because there is not one. A
    conduit whose endpoints are not both in the shapefile is dropped and counted.
    """
    pts = gpd.read_file(ROOT / "swmm" / "gp" / "gis" / "gp_junctions.shp").to_crs(CRS)
    xy = {r["Name"]: (r.geometry.x, r.geometry.y) for _, r in pts.iterrows()}
    lines, dropped = [], 0
    for r in _sections(ROOT / "swmm" / "gp" / "gp_sewer.inp", "CONDUITS"):
        if len(r) >= 3 and r[1] in xy and r[2] in xy:
            lines.append(LineString([xy[r[1]], xy[r[2]]]))
        else:
            dropped += 1
    return pts, gpd.GeoDataFrame(geometry=lines, crs=CRS), dropped


def mesh_edges(res, bbox):
    """Mesh edges with at least one node inside the plotting window.

    The grids span the whole of Long Island Sound and the coupling region is a
    corner of it, so drawing every edge would be both illegible and slow.
    """
    cp = pl.Path(get_dflow_control_path("gp", res))
    net = cp.parent / f"{get_dflow_grid_name(cp)}.nc"
    grid = xugrid.Ugrid2d.from_dataset(xugrid.open_dataset(net).ugrid.to_dataset())
    xy = grid.node_coordinates
    x0, y0, x1, y1 = bbox
    inside = (xy[:, 0] >= x0) & (xy[:, 0] <= x1) & (xy[:, 1] >= y0) & (xy[:, 1] <= y1)
    ec = grid.edge_node_connectivity
    keep = inside[ec[:, 0]] | inside[ec[:, 1]]
    return xy[ec[keep]], grid.n_face


def make():
    bnd = gpd.read_file(
        ROOT / "modflow" / "gis" / "gp" / "gp_chd_chd_surface_utm18n.shp").to_crs(CRS)
    active = gpd.read_file(
        ROOT / "modflow" / "gis" / "gp" / "gp_onshore_offshore_utm18n.shp").to_crs(CRS)
    pts, pipes, dropped = sewer_network()
    print(f"sewer: {len(pts)} junctions, {len(pipes)} conduits drawn, {dropped} dropped")

    outline = active.dissolve().boundary
    x0, y0, x1, y1 = active.total_bounds
    bbox = (x0 - MARGIN, y0 - MARGIN, x1 + MARGIN, y1 + MARGIN)

    with styles.USGSMap():
        fig, axs = plt.subplots(ncols=3, figsize=(7.5, 3.1), layout="constrained")
        for ax, (res, label) in zip(axs, GRIDS):
            seg, nface = mesh_edges(res, bbox)
            ax.set_xlim(bbox[0], bbox[2])
            ax.set_ylim(bbox[1], bbox[3])
            # Basemap first, so it sits under everything, and tolerated if absent:
            # the tiles are fetched over the network and a co-author rebuilding the
            # document offline should still get the figure, just without context.
            # attribution=False by intent, not oversight: the credit belongs in the
            # figure caption, where a reader of the typeset document will find it,
            # rather than burned into the image at tile-label size. The caption
            # carries the provider's own string, cx_provider["attribution"].
            # zoom=14 rather than the level contextily picks for this extent, 13,
            # for two reasons. At 13 the tiles carry a bold "SUFFOLK COUNTY" that
            # the top right of the frame cuts through, and the label cannot be
            # brought inside: it is long enough that containing it would need
            # several more kilometers of margin, shrinking the coupling region to
            # make room for a county name. At 14 the county label gives way to
            # local place names, which are set small enough at this size to read as
            # map texture. The tiles are also twice the resolution -- 7.2 against
            # 14.4 m per pixel here -- which is the right side of the 12.6 m a
            # 2.3 inch panel needs at 300 dpi.
            try:
                cx.add_basemap(ax, crs=CRS, source=cx_provider, attribution=False,
                               zoom=14)
            except Exception as exc:
                print(f"  basemap unavailable for {res} ({type(exc).__name__}); "
                      "drawing without it")
            ax.add_collection(LineCollection(seg, colors=C_MESH, linewidths=0.25,
                                             zorder=1))
            # Dissolved to one outline. Drawn per cell, its 1,455 boundaries read as
            # a second mesh and compete with the one the figure is about.
            outline.plot(ax=ax, color="0.25", linewidth=0.5, zorder=2)
            bnd.plot(ax=ax, color=C_BND, linewidth=0, alpha=0.85, zorder=3)
            pipes.plot(ax=ax, color=C_PIPE, linewidth=0.8, zorder=4)
            pts.plot(ax=ax, color=C_JUNC, markersize=0.9, zorder=5)
            ax.set_xlim(bbox[0], bbox[2])
            ax.set_ylim(bbox[1], bbox[3])
            ax.set_aspect("equal")
            ax.set_xticks([])
            ax.set_yticks([])
            styles.heading(ax=ax, letter="ABC"[GRIDS.index((res, label))],
                           heading=f"{label}, {nface:,} cells", fontsize=7.5)
        # One scale bar: the three panels share an extent.
        ax = axs[0]
        bar = 2000.0
        xb = bbox[0] + 0.08 * (bbox[2] - bbox[0])
        yb = bbox[1] + 0.07 * (bbox[3] - bbox[1])
        ax.plot([xb, xb + bar], [yb, yb], "-", color="black", lw=1.2, zorder=6)
        ax.annotate("2 km", xy=(xb + bar / 2, yb), xytext=(0, 2),
                    textcoords="offset points", ha="center", fontsize=6.5)

        handles = [
            plt.Line2D([], [], color=C_MESH, lw=0.6, label="D-Flow FM mesh"),
            plt.Line2D([], [], color=C_BND, lw=3, label="MODFLOW 6 coastal boundary"),
            plt.Line2D([], [], color=C_PIPE, lw=1.0, label="Sewer conduit"),
            plt.Line2D([], [], color=C_JUNC, lw=0, marker="o", ms=2.5,
                       label="Sewer junction"),
        ]
        leg = fig.legend(handles, [h.get_label() for h in handles],
                         loc="outside lower center", ncol=4, frameon=False,
                         prop={"weight": "bold", "size": 7.5})
        styles.graph_legend_title(leg, fontsize=7.5)
        fig.savefig(OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    make()
