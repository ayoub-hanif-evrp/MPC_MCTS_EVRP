"""Conservative resource limits for independent experiment workers."""

import ctypes
import json
import os
import platform
import subprocess


def physical_cores():
    if os.name == "nt":
        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Processor | Measure-Object NumberOfCores -Sum).Sum"],
            text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        return max(1, int(output.strip()))
    try:
        from pathlib import Path
        cores = set()
        for block in Path("/proc/cpuinfo").read_text().split("\n\n"):
            values = dict(line.split(":", 1) for line in block.splitlines() if ":" in line)
            values = {k.strip(): v.strip() for k, v in values.items()}
            if "core id" in values:
                cores.add((values.get("physical id", "0"), values["core id"]))
        if cores:
            return len(cores)
    except OSError:
        pass
    return max(1, (os.cpu_count() or 2) // 2)


def available_memory_mib():
    if os.name == "nt":
        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in
                ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]
        status = Status()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError("Unable to measure free physical memory")
        return status.available / 1024**2
    from pathlib import Path
    values = dict(line.split(":", 1) for line in Path("/proc/meminfo").read_text().splitlines())
    return int(values["MemAvailable"].split()[0]) / 1024


def peak_memory_mib():
    if os.name == "nt":
        class Counters(ctypes.Structure):
            _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
                (name, ctypes.c_size_t) for name in
                ("peak", "working", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "page", "peak_page")]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        handle = ctypes.windll.kernel32.GetCurrentProcess
        handle.restype = ctypes.c_void_p
        function = ctypes.windll.psapi.GetProcessMemoryInfo
        function.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        if not function(handle(), ctypes.byref(counters), counters.cb):
            raise OSError("Unable to measure process memory")
        return counters.peak / 1024**2
    import resource
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2 if platform.system() == "Darwin" else 1024)


def worker_capacity(measured_peak_mib=256, requested=4):
    cores, free = physical_cores(), available_memory_mib()
    per_worker = max(256, measured_peak_mib * 1.5)
    memory_limit = max(0, int((free - 512) // per_worker))
    workers = min(max(1, requested), max(1, cores-1), memory_limit)
    return dict(workers=workers, physical_cores=cores, available_memory_mib=free,
                measured_peak_mib=measured_peak_mib, reserved_mib=512,
                per_worker_mib=per_worker, numerical_threads=1)
