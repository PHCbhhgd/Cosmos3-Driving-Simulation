"""Refuse a launch if any selected physical GPU is already doing compute."""

import argparse
import csv
import io
import json
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("--gpus", required=True)
args = parser.parse_args()
selected = args.gpus.split(",")
if len(selected) != 4 or len(set(selected)) != 4 or not all(x.isdigit() for x in selected):
    parser.error("Select exactly four distinct physical GPU indices")


def query(arguments):
    output = subprocess.check_output(
        ["nvidia-smi", *arguments, "--format=csv,noheader,nounits"], text=True
    )
    return [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(output))]


devices = query(["--query-gpu=index,uuid,memory.used,memory.total,utilization.gpu"])
processes = query(["--query-compute-apps=gpu_uuid,pid,used_gpu_memory,process_name"])
report = []
for index in selected:
    device = next((row for row in devices if row[0] == index), None)
    if device is None:
        parser.error(f"Physical GPU {index} does not exist")
    _, uuid, used, total, utilization = device
    active = [row[1:] for row in processes if row[0] == uuid]
    blocking = active
    idle = not blocking and int(used) < 1024 and int(utilization) <= 5
    report.append(
        dict(
            index=int(index),
            memory_used_mib=int(used),
            memory_total_mib=int(total),
            utilization=int(utilization),
            compute_processes=active,
            available=idle,
        )
    )
print(json.dumps({"gpus": report, "available": all(row["available"] for row in report)}, indent=2))
if not all(row["available"] for row in report):
    raise SystemExit("Selected GPUs are busy; no inference process was started")
