"""grep vs ripgrep vs ugrep timing. Output is piped through `wc -l` (never to /dev/null,
which GNU grep short-circuits) so every match is produced and counts can be checked."""
import statistics, subprocess, sys, time

CORPUS, UGREP, CLAUDE = sys.argv[1:4]
RUNS = 7
TREE = f"{CORPUS}/linux"
BIG = f"{CORPUS}/big.txt"
X = "-rnI --exclude-dir=.git"  # grep/ugrep: match rg defaults (skip .git, skip binary)

# tool -> (tree prefix, file prefix); pattern + path appended
TOOLS = {
    "grep":     (f"/usr/bin/grep {X}",                   "/usr/bin/grep -n"),
    "rg":       ("/usr/bin/rg -n",                       "/usr/bin/rg -n"),
    "rg -j1":   ("/usr/bin/rg -n -j1",                   None),
    "ugrep":    (f"{UGREP} {X}",                         f"{UGREP} -n"),
    "ugrep -J1": (f"{UGREP} {X} -J1",                    None),
    "ugrep(cc)": (f"exec -a ugrep {CLAUDE} {X}",         f"exec -a ugrep {CLAUDE} -n"),
}
CASES = [
    ("tree: literal",       "tree", "PM_RESUME"),
    ("tree: literal -i",    "tree", "-i PM_RESUME"),
    ("tree: regex -w",      "tree", "-wE '[A-Z]+_SUSPEND'"),
    ("tree: alternation",   "tree", "-E 'ERR_SYS|PME_TURN_OFF|LINK_REQ_RST|CFG_BME_EVT'"),
    ("tree: no match",      "tree", "zqxjvnomatch"),
    ("file: literal",       "file", "PM_RESUME"),
    ("file: literal -i",    "file", "-i PM_RESUME"),
    ("file: regex \\w+_init(", "file", "-E '\\w+_init\\('"),
    ("file: no match",      "file", "zqxjvnomatch"),
    ("startup (tiny file)", "tiny", "zqxjvnomatch"),
]

def time_cmd(cmd):
    full = f"({cmd}) | wc -l"
    out = subprocess.run(["bash", "-c", full], capture_output=True, text=True).stdout.strip()  # warmup
    ts = []
    for _ in range(RUNS):
        t = time.perf_counter()
        subprocess.run(["bash", "-c", full], stdout=subprocess.DEVNULL)
        ts.append(time.perf_counter() - t)
    return statistics.median(ts), int(out)

print("case\t" + "\t".join(TOOLS) + "\thits(per tool)")
ONLY = sys.argv[4] if len(sys.argv) > 4 else ""
for name, kind, pat in CASES:
    if ONLY and ONLY not in name: continue
    row, hits = [], []
    for tool, (tp, fp) in TOOLS.items():
        prefix = tp if kind == "tree" else fp
        if prefix is None:
            row.append("-"); continue
        target = {"tree": TREE, "file": BIG, "tiny": f"{CORPUS}/linux/COPYING"}[kind]
        p = pat.replace("-wE", "-w").replace("-E ", "") if tool.startswith("rg") else pat  # rg -E = --encoding
        med, n = time_cmd(f"{prefix} {p} {target}")
        row.append(f"{med:.3f}"); hits.append(n)
    print(f"{name}\t" + "\t".join(row) + f"\t{hits}", flush=True)
