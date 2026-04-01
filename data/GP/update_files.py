import pathlib as pl

ws = pl.Path(".")
files = sorted(list(ws.glob("*.tim")))

for file in files[:]:
    print(f"processing...'{file}'")
    with open(file, "r") as f:
        lines = f.readlines()

    with open(file, "w") as f:
        for idx, line in enumerate(lines):
            t = line.split()
            line = f"{t[0]} {t[1]} 1000.0\n"
            f.write(line)
            
