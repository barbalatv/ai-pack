"""Run with a clean virtualenv's Python -I, outside the repository checkout."""

import os
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import xml.etree.ElementTree as ET

import aipack
from aipack import pack_project


def main() -> None:
    package = Path(aipack.__file__).resolve()
    if sys.prefix == sys.base_prefix or not package.is_relative_to(Path(sys.prefix).resolve()):
        raise RuntimeError(f"Expected a virtualenv-installed package, got {package}")
    cli = Path(sysconfig.get_path("scripts")) / ("ai-pack.exe" if os.name == "nt" else "ai-pack")
    env = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
    with tempfile.TemporaryDirectory(prefix="ai-pack-smoke-", dir=Path.cwd()) as directory:
        root = Path(directory).resolve()
        if not root.is_relative_to(Path.cwd().resolve()):
            raise RuntimeError("Smoke directory escaped the working directory")
        subprocess.run([str(cli), "--help"], cwd=root, env=env, check=True)
        sample = root / "sample"
        sample.mkdir()
        source = "print(123)\n"
        (sample / "hello.py").write_text(source, encoding="utf-8")
        output = root / "bundle.txt"
        subprocess.run(
            [str(cli), str(sample), "--no-config", "--lang", "en", "--output", str(output)],
            cwd=root, env=env, check=True,
        )
        bundle = output.read_text(encoding="utf-8")
        assert "FILE: hello.py" in bundle and source in bundle, "Installed CLI lost sample content"
        result = pack_project(sample, no_config=True)
        assert result.files_included == 1 and source.strip() in result.bundle
        assert ET.fromstring(result.bundle).tag == "project_bundle", "API default must remain XML"
    print(f"Installed CLI/API smoke passed: {package}")


if __name__ == "__main__":
    main()
