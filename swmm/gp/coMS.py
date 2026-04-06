# Package imports
import platform
import flopy
import pathlib as pl
from modflowapi import ModflowApi
from modflowapi.extensions import ApiSimulation
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


import pyswmm
# ---------------- Documentation --------------------------------------------------------------
# Mappings the nodes of interactions in SWMM
junctions = (
    "PS1", "PS2", "PS3", "PS4", "PS5","PS6",
)

swmm_nodes = {}

# Mappings the nodes of interactions in MODFLOW
mf6_cells = {
    "PS1": (24, 32), "PS2": (27, 32), "PS3": (30, 31), "PS4": (34, 25), "PS5": (27, 29),"PS6": (23, 22),
}


if platform.system().lower() == "windows":
    libmf6_pth = "../bin/"
    ext = ".dll"
elif platform.system().lower() == "linux":
    libmf6_pth = "../bin/"
    ext = ".so"
else:
    libmf6_pth = "../bin/"
    ext = ".dylib"
libmf6_exe = pl.Path(f"{libmf6_pth}libmf6{ext}").absolute()

name = "MODFLOW"
sim = flopy.mf6.MFSimulation.load(
    sim_ws=".",
    verbosity_level=0,
)
gwf = sim.get_model(name)
#mg = gwf.modelgrid

# Initialize MODFLOW
mf6 = ModflowApi(".\\bin\\libmf6.dll")
mf6.initialize()
current_time = mf6.get_current_time()
end_time = mf6.get_end_time()

# Use recent MODFLOWAPI functionality for accessing data from the API in flopy-like data structures
apisim = ApiSimulation.load(mf6)
apiml = apisim.get_model()

# Get a handle to the WELL package to get SWMM fluxes
sewer_flow = apiml.get_package("SWMM")

# Initialize SWMM
ts = 60  # s, time step
t15d = ts * 24 * 15 * 60  # s, step advance of swmm = stress period
tmax = 24 * 60 * (end_time + 1)  # min
time = np.arange(1, tmax, 1)  # min
iswmm = 1  # index in the swmm simulation arrays
simsw = pyswmm.Simulation("Case2.inp")

# Build the swmm_nodes dictionary where the values are the SWMM node objects and outlet
for j in junctions:
    swmm_nodes[j] = pyswmm.Nodes(simsw)[j]

Out1 = pyswmm.Nodes(simsw)["O3"]  # This is the outlet into the WWTP

out_array = np.zeros(365)  # vector to record flow rate

# MODFLOW ----------------
# create array of zeros to fill with active heads
time_vec = np.zeros(365)

# Store SWMM heads for each day
swmm_daily_heads = {}
simsw.start()
j = 0
while True:
    if simsw._terminate_request == True:
        break
    else:
        while current_time < end_time:
            # dt = mf6.get_time_step()
            mf6.update()
            current_time = mf6.get_current_time()
            dt = 1
            print(f"Current Time: {current_time}, dt: {dt}")

            with flopy.utils.HeadFile('./gwf.hds',
                                        text='head') as hdobj:  # Grab the hydraulic head of the top layer
                head2D = hdobj.get_data(totim=current_time)[0]
                head2D[head2D == 1e30] = 0  # Change the "no data" value
            heads = apiml.X
            time_vec[j] = np.array(current_time)

            # Exchange fluxes calculation
            mf6_spd = []
            for key, value in swmm_nodes.items():
                #print(f"mf6_cells[{key}] =", mf6_cells.get(key, "Key not found"))
                row, col = mf6_cells[key]
                #head = heads[0, row, col]
                head = heads[0, row, col]
                #print(head)
                # ft
                #  Hydraulic head of the water within the sewer at the node
                #
                # Use real-time SWMM head instead of stored daily value
                # Accumulate SWMM head for each day
                if int(current_time) % 86400 == 0:  #
                    # Store SWMM head for the node
                    swmm_daily_heads[key] = swmm_nodes[key].head
                # Get the SWMM head for the current day
                #swmm_head = swmm_daily_heads.get(key, 0)
                swmm_head = swmm_daily_heads.get(key, swmm_nodes[key].head)
                #swmm_head = swmm_nodes[key].head
                delta_h= (head * 0.304) - swmm_head  # Get SWMM head at the same time
                # m

                # Calculation of the Infiltration and Exfiltration
                if delta_h > 0.0:
                    Q = delta_h * 0.004 # m3/s
                else:
                    Q = delta_h * 0.000287  # m3/s
                    swmm_flow = swmm_nodes[key].total_inflow  #
                    if swmm_flow - Q < 0:
                        Q = 0

                value.generated_inflow(Q)  # m3/s (CMS): Flux for SWMM
                mf6_spd.append(((0, row, col), -Q * 35.315))  # ft3/s (CFS): Flux for MODFLOW

            # update SWMM well file with new flux data
            dtype = [("nodelist", "O"), ("q", float)]
            sewer_flow.stress_period_data.values = np.array(mf6_spd, dtype=dtype)

            # SWMM -----------------------------------------------
            simsw.step_advance(int(dt * 3600 * 24))

            out_array[j] = np.array(Out1.total_inflow)

            print(f"Flow at time {current_time}: {out_array[j]}")
            j += 1
            try:
                simsw.__next__()  # seconds
            except StopIteration:
                break
            print(f"finished...{simsw.current_time}")
    simsw._terminate_request = True

try:
    mf6.finalize()
    success = True
except:
    raise RuntimeError

simsw.__exit__()

# Saving sewer outflow results
# ----------------------------
np.save("171_flow_inf_c", out_array)

# Get MODFLOW head and SWMM well data from output
obs_loc = [(0, row, col) for (row, col) in mf6_cells.values()]
hobj = gwf.output.head()
head_obs = hobj.get_ts(obs_loc)
bobj = gwf.output.budget()
sewer_obs = []
for t in bobj.get_times():
    v = bobj.get_data(totim=t, text="WEL")[1]
    temp = [t]
    for q in v["q"]:
        temp.append(q)
    temp = temp[:len(junctions) + 1]  #  dtype

    sewer_obs.append(tuple(temp))
dtype = [("time", float)]
dtype += [(j, float) for j in junctions]
sewer_obs = np.array(sewer_obs, dtype=dtype)

# Plotting flow exchanges
# -----------------------
fig, ax = plt.subplots(figsize=(8, 6))
# ax[1].set_title("Flow exchange")
for j in junctions:
    plt.plot(
        sewer_obs["time"],
        -sewer_obs[j],
        "-",
        lw=2,
        label=j,
    )
plt.legend(loc="best", ncol=6, frameon=False)
plt.xlim(0, 365)
plt.xlabel("time, day")
plt.ylabel("Flow exchange (I & E), ft\u00b3/s")
plt.show()

# Plotting flow exchanges in cubic meters per second (m³/s)
fig, ax = plt.subplots(figsize=(8, 6))
for j in junctions:
    plt.plot(
        sewer_obs["time"],
        -sewer_obs[j] * 0.0283168,  #  ft³/s به m³/s
        "-",
        lw=2,
        label=j,
    )
plt.legend(loc="best", ncol=6, frameon=False)
plt.xlim(0, 365)
plt.xlabel("time, day")
plt.ylabel("Flow exchange (I & E), m³/s")
plt.savefig("flow_exchange_CMS.png", dpi=1200, bbox_inches="tight")
plt.show()

# Save flow exchange data in cubic meters per second (m³/s) to CSV
flow_exchange_data = {"Time": sewer_obs["time"]}
for j in junctions:
    flow_exchange_data[j] = -sewer_obs[j] * 0.0283168  #  ft³/s به m³/s

df_flow_exchange = pd.DataFrame(flow_exchange_data)
df_flow_exchange.to_csv("flow_exchange_m3s.csv", index=False)
print("Flow exchange data saved in 'flow_exchange_m3s.csv'")

# Plotting flow exchanges (second plot)
# -----------------------
fig, ax = plt.subplots(figsize=(8, 6))
# ax[1].set_title("Flow exchange")
for j in junctions:
    plt.plot(
        sewer_obs["time"],
        -sewer_obs[j] * 1000 / 0.25 * 0.304,
        "-",
        lw=2,
        label=j,
    )
plt.legend(loc="best", ncol=6, frameon=False)
plt.xlim(0, 365)
plt.xlabel("time, day")
plt.ylabel("Flow exchange (I & E), L/(s km)")
plt.show()

# Display results from the saved file "171_flow_inf_c"
flow_data = np.load("171_flow_inf_c.npy")
print("Results from 171_flow_inf_c:")
print(flow_data)

# np.savetxt("flow_results.csv", flow_data, delimiter=",", header="Flow Values", comments="")
df = pd.DataFrame({"Time Step": np.arange(len(flow_data)), "Flow": flow_data})
df.to_csv("flow_results_detailed.csv", index=False)

# Plot results (third plot)
fig, ax = plt.subplots(figsize=(8, 6))
plt.plot(flow_data, '-o', color='blue')
plt.title("Flow Results from O3")
plt.xlabel("Time Steps")
plt.ylabel("Flow Values")
plt.show()

# Observed data
observed_days = [15, 45, 75, 105, 135, 165, 195, 225, 255, 285, 315, 345]
observed_values = [0.012443, 0.014502, 0.024579, 0.019891, 0.012706, 0.012706,
                    0.013582, 0.01402, 0.013144, 0.011698, 0.010822, 0.010997]

# Number of days in each month (non-leap year)
yearmin = np.array([31, 28, 30, 30, 31, 30, 31, 31, 30, 31, 30, 31])
# Compute the cumulative sum of days to determine month ranges
cumulative_days = np.cumsum(yearmin)
# Calculate the simulated monthly average flow
simulated_values = [flow_data[start:end].mean() for start, end in
                    zip(np.hstack(([0], cumulative_days[:-1])), cumulative_days)]

# Save the simulated monthly average flow to CSV
import pandas as pd
months = np.arange(1, 13)
df_simulated = pd.DataFrame({
    "Month": months,
    "Simulated_Avg_Flow": simulated_values
})
df_simulated.to_csv("simulated_monthly_avg.csv", index=False)
print("Simulated monthly average flow saved to 'simulated_monthly_avg.csv'")

# Map observed data to corresponding months
months = np.searchsorted(cumulative_days, observed_days)

# Plot the comparison of simulated and observed results (fourth plot)
fig, ax = plt.subplots(figsize=(8, 6))
plt.plot(observed_days, simulated_values, label="Simulated", marker="o", color="black")
plt.plot(observed_days, observed_values, label="Observed", linestyle="--", marker="o", color="black")
plt.xlabel("Days", color="black")
plt.ylabel("Flow (CMS)", color="black")
plt.tick_params(axis='both', colors='black')
plt.legend(frameon=False, loc="best", fontsize=10)

# Calculate error
simulated_values = np.array(simulated_values)
observed_values = np.array(observed_values)
error = np.sum((simulated_values - observed_values) ** 2)
plt.title(f"(Error={error:.6f})")

plt.savefig("flow_comparison.png", dpi=1200, bbox_inches="tight")
plt.show()