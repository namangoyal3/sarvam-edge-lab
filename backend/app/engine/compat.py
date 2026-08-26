"""Device × model compatibility: compatible | compatible_with_warning | incompatible."""
ARCH_BY_CHIPSET = {
    # crude architecture classes; enough for a demo matrix
    "helio g85": "arm64", "snapdragon 695": "arm64", "tensor g3": "arm64",
    "a15 bionic": "arm64", "m1": "arm64", "m2": "arm64", "exynos 1330": "arm64",
    "core i5-1135g7": "x86_64", "ryzen 5 5500u": "x86_64", "core i7-8550u": "x86_64",
    "jetson orin nano": "arm64", "rk3588": "arm64",
}
GPU_HINT = {"adreno 619": "adreno", "immortalis-g715": "immortalis", "apple gpu (4-core)": "apple-gpu",
            "iris xe": "iris-xe", "mali-g57": "mali"}


def check(device: dict, model: dict) -> dict:
    import json as J
    reasons = []
    if model.get("kind") == "cloud_ref":
        return {"status": "compatible_with_warning",
                "reasons": ["cloud reference model: execution depends on network + policy, not device hardware"]}
    if model.get("kind") in ("fixture", "classifier"):
        return {"status": "compatible", "reasons": ["lightweight on-device runtime; runs on any enrolled device"]}

    supported_os = J.loads(model.get("supported_os") or "[]")
    chipsets = [c.lower() for c in J.loads(model.get("supported_chipsets") or "[]")]
    runtimes = J.loads(model.get("supported_runtimes") or "[]")

    if device["ram_gb"] < model["min_ram_gb"]:
        reasons.append(f"RAM {device['ram_gb']}GB < required {model['min_ram_gb']}GB")
    elif model.get("recommended_ram_gb") and device["ram_gb"] < model["recommended_ram_gb"]:
        reasons.append(f"RAM {device['ram_gb']}GB below recommended {model['recommended_ram_gb']}GB — expect slower inference")

    dev_os = device["os"].lower()
    os_family = dev_os.split()[0]
    if supported_os and not any(o.lower().startswith(os_family.split("-")[0][:5]) for o in supported_os):
        reasons.append(f"OS '{device['os']}' not in supported list {supported_os}")

    if runtimes and device["runtime"] not in runtimes:
        reasons.append(f"runtime '{device['runtime']}' not supported (needs one of {runtimes})")

    chipset = device["chipset"].lower()
    arch = ARCH_BY_CHIPSET.get(chipset, None)
    tested = chipset in chipsets
    if not tested:
        if arch in ("arm64", "x86_64"):
            reasons.append(f"chipset '{device['chipset']}' untested but arch ({arch or 'unknown'}) matches target class")
        else:
            reasons.append(f"chipset '{device['chipset']}' unknown architecture — cannot verify")

    if reasons:
        hard = [r for r in reasons if "< required" in r or "not in supported list" in r
                or "not supported" in r or "cannot verify" in r]
        status = "incompatible" if hard else "compatible_with_warning"
    else:
        status = "compatible"
        reasons.append("all requirements met")
    return {"status": status, "reasons": reasons}
