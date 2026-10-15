"""GPU: NVIDIA pres nvidia-smi, jinak AMD pres /sys/class/drm."""

import glob
import os
import shutil
import subprocess

NVIDIA_QUERY = "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu"
AMD_BUSY_GLOB = "/sys/class/drm/card*/device/gpu_busy_percent"


def get_gpu():
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", NVIDIA_QUERY, "--format=csv,noheader,nounits"],
                text=True, stderr=subprocess.DEVNULL).strip().splitlines()[0]
            util, used, total, temp = [x.strip() for x in out.split(",")]
            return {
                "available": True, "vendor": "NVIDIA",
                "util": float(util),
                "mem_used": float(used), "mem_total": float(total),
                "temp": float(temp),
            }
        except Exception:
            pass

    busy_files = glob.glob(AMD_BUSY_GLOB)
    if busy_files:
        try:
            path = busy_files[0]
            dev = os.path.dirname(path)
            with open(path) as f:
                util = float(f.read().strip())
            gpu = {"available": True, "vendor": "AMD", "util": util}
            try:
                with open(os.path.join(dev, "mem_info_vram_used")) as f:
                    gpu["mem_used"] = int(f.read().strip()) / 1024**2
                with open(os.path.join(dev, "mem_info_vram_total")) as f:
                    gpu["mem_total"] = int(f.read().strip()) / 1024**2
            except Exception:
                pass
            for hwmon in glob.glob(os.path.join(dev, "hwmon", "hwmon*", "temp1_input")):
                try:
                    with open(hwmon) as f:
                        gpu["temp"] = float(f.read().strip()) / 1000.0
                    break
                except Exception:
                    pass
            return gpu
        except Exception:
            pass

    return {"available": False}
