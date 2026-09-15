"""Measure authorable source reachability from generated genmake2 symlinks."""

import json
import os

import config


def main():
    profiles = sorted(set(config.BUILD_PROFILE.values()))
    mapping = {}
    evidence = {}
    for relpath in config.PHYSICS_FILES:
        target = os.path.realpath(os.path.join(config.BASE, relpath))
        live_profiles = []
        links = {}
        for profile in profiles:
            build_dir = os.path.join(config.BUILDS, profile)
            matched = []
            for name in os.listdir(build_dir):
                path = os.path.join(build_dir, name)
                if os.path.islink(path) and os.path.realpath(path) == target:
                    matched.append(name)
            if matched:
                live_profiles.append(profile)
                links[profile] = sorted(matched)
        rows = [check for check in config.ROW_ORDER
                if config.BUILD_PROFILE[check] in live_profiles]
        mapping[relpath] = rows
        evidence[relpath] = {"profiles": live_profiles, "build_links": links}
    payload = {
        "method": "resolved source targets of symlinks emitted by each calibrated genmake2 build",
        "commit": config.MITGCM_COMMIT,
        "rows": mapping,
        "evidence": evidence,
    }
    with open(config.FILE_ROWS, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, sort_keys=True)
        handle.write("\n")
    dead = [path for path, rows in mapping.items() if not rows]
    print(f"{len(mapping) - len(dead)}/{len(mapping)} authorable files compiled; "
          f"dead={dead}")


if __name__ == "__main__":
    main()
