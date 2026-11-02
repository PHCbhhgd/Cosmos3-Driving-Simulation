"""Small four-GPU NCCL collective check, no model allocation."""

import os
import time
from datetime import timedelta
import torch
import torch.distributed as dist

rank = int(os.environ["LOCAL_RANK"])
torch.cuda.set_device(rank)
dist.init_process_group(
    "nccl", timeout=timedelta(seconds=90), device_id=torch.device(f"cuda:{rank}")
)
x = torch.tensor([dist.get_rank() + 1.0], device=f"cuda:{rank}")
dist.all_reduce(x)
torch.cuda.synchronize()
assert x.item() == 10.0
print(f"rank {rank}: NCCL all_reduce passed (sum={x.item()})", flush=True)
groups = [dist.new_group(list(range(4))) for _ in range(3)]
for index, group in enumerate([dist.group.WORLD, *groups]):
    objects = [None] * 4
    dist.all_gather_object(objects, {"rank": rank, "payload": "metadata" * 10000}, group=group)
    assert [obj["rank"] for obj in objects] == list(range(4))
    print(f"rank {rank}: group {index} all_gather_object passed", flush=True)
if os.environ.get("COSMOS3_BENCHMARK_COLLECTIVES") == "1":
    source = torch.ones(4 * 1024 * 1024, dtype=torch.float32, device=f"cuda:{rank}")
    target = torch.empty(4 * len(source), dtype=source.dtype, device=source.device)
    for _ in range(3):
        dist.all_gather_into_tensor(target, source)
    torch.cuda.synchronize()
    started = time.perf_counter()
    for _ in range(10):
        dist.all_gather_into_tensor(target, source)
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - started
    assert torch.all(target == 1)
    print(f"rank {rank}: 10 x 16 MiB all_gather input: {elapsed:.4f} seconds", flush=True)
dist.destroy_process_group()
