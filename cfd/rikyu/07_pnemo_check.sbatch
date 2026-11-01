#!/bin/bash
# PhysicsNeMo container check on one GPU: versions, GPU, the PINN pieces (Sym, folded into the core package in 26.05),
# and a tiny training step, timed.
#   sbatch -A $ACCT cfd/rikyu/07_pnemo_check.sbatch          (from $W; the image is $W/images/physicsnemo-<tag>.sif)
#SBATCH --job-name=cfd-pnemo
#SBATCH --time=00:30:00
#SBATCH --nodes=1
#SBATCH --gpus=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --output=logs/%x-%j.log
set -eo pipefail
IMG=${IMG:-$(ls "$W"/images/physicsnemo-*.sif | tail -1)}
echo "image $IMG"
apptainer exec --nv "$IMG" python - <<'EOF'
import importlib, pkgutil, time
import torch
print("torch", torch.__version__, "cuda", torch.version.cuda, "available", torch.cuda.is_available())
print("device", torch.cuda.get_device_name(0), "bf16", torch.cuda.is_bf16_supported())
import physicsnemo
print("physicsnemo", getattr(physicsnemo, "__version__", "?"))
subs = sorted(m.name for m in pkgutil.iter_modules(physicsnemo.__path__))
print("submodules", subs)
for name in ("physicsnemo.sym", "physicsnemo_sym", "physicsnemo.sym.eq.pdes.navier_stokes",
             "physicsnemo.models.transolver", "physicsnemo.models.meshgraphnet", "physicsnemo.models.domino",
             "physicsnemo.models.fno"):
    try:
        importlib.import_module(name); print("ok  ", name)
    except Exception as e:
        print("miss", name, type(e).__name__, str(e)[:120])
# a small MLP fitted to sin(x) by autograd of a PDE-style residual, to time a PINN-like step
net = torch.nn.Sequential(torch.nn.Linear(2, 256), torch.nn.SiLU(), *[m for _ in range(4) for m in (torch.nn.Linear(256, 256), torch.nn.SiLU())],
                          torch.nn.Linear(256, 3)).cuda()
opt = torch.optim.Adam(net.parameters(), 1e-3)
x = torch.rand(65536, 2, device="cuda", requires_grad=True)
torch.cuda.synchronize(); t0 = time.time()
for it in range(200):
    out = net(x)
    g = torch.autograd.grad(out[:, 0].sum(), x, create_graph=True)[0]
    gg = torch.autograd.grad(g[:, 0].sum(), x, create_graph=True)[0]
    loss = ((gg[:, 0] + torch.sin(x[:, 0])) ** 2).mean()
    opt.zero_grad(); loss.backward(); opt.step()
torch.cuda.synchronize()
print("PINN-like step (65k points, 5x256 MLP, 2nd derivatives): %.1f ms" % ((time.time() - t0) / 200 * 1e3))
EOF
