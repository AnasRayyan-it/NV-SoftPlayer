# -*- coding: UTF-8 -*-
"""
Build script to package the NV-SoftPlayer NVDA add-on.
Creates lightweight .nvda-addon and .zip packages (approx 50 KB).
External playback binaries (yt-dlp and ffmpeg) are automatically downloaded
by the add-on on first run into the bin folder.
Pass --bundle-binaries to bundle local executables if needed.
"""

import os
import sys
import shutil
import zipfile


def parse_manifest(manifest_path):
	data = {}
	if not os.path.isfile(manifest_path):
		return data
	with open(manifest_path, "r", encoding="utf-8") as f:
		for line in f:
			line = line.strip()
			if not line or line.startswith("#"):
				continue
			if "=" in line:
				key, val = line.split("=", 1)
				key = key.strip()
				val = val.strip().strip('"').strip("'")
				data[key] = val
	return data


def build(bundle_binaries=False):
	root_dir = os.path.abspath(os.path.dirname(__file__))
	manifest_path = os.path.join(root_dir, "manifest.ini")

	if not os.path.isfile(manifest_path):
		print("[ERROR] manifest.ini not found in:", root_dir)
		sys.exit(1)

	manifest = parse_manifest(manifest_path)
	addon_name = manifest.get("name", "NV-SoftPlayer")
	addon_version = manifest.get("version", "1.0.0")

	output_addon = os.path.join(root_dir, f"{addon_name}-{addon_version}.nvda-addon")
	output_zip = os.path.join(root_dir, f"{addon_name}-{addon_version}.zip")

	print("=" * 60)
	mode_str = "Bundled Binaries" if bundle_binaries else "Lightweight (Auto-Downloads on 1st run)"
	print(f"Building NVDA Add-on: {addon_name} v{addon_version} [{mode_str}]")
	print("=" * 60)

	ignored_dirs = {"__pycache__", ".git", ".vscode", ".idea", "dist", "build"}
	ignored_exts = {".pyc", ".pyo", ".nvda-addon", ".zip", ".delete"}
	ignored_files = {"build_addon.py", "build_addon.ps1"}

	if not bundle_binaries:
		ignored_files.update({"ffmpeg.exe", "yt-dlp.exe"})

	print("\nCompressing files into installer package...")
	count = 0
	with zipfile.ZipFile(output_addon, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
		for dirpath, dirnames, filenames in os.walk(root_dir):
			dirnames[:] = [d for d in dirnames if d not in ignored_dirs]
			for filename in filenames:
				if filename in ignored_files:
					continue
				_, ext = os.path.splitext(filename)
				if ext.lower() in ignored_exts:
					continue
				abs_file = os.path.join(dirpath, filename)
				if abs_file in (output_addon, output_zip):
					continue
				rel_path = os.path.relpath(abs_file, root_dir).replace("\\", "/")
				zf.write(abs_file, rel_path)
				count += 1
				print(f"  + {rel_path}")

	# Also create a .zip copy for platforms that do not recognize .nvda-addon
	shutil.copyfile(output_addon, output_zip)

	size_kb = os.path.getsize(output_addon) / 1024
	print("-" * 60)
	print("[SUCCESS] Package created successfully!")
	print(f"Add-on: {output_addon} ({size_kb:.1f} KB)")
	print(f"ZIP:    {output_zip} ({size_kb:.1f} KB)")
	print(f"Files included: {count}")

	desktop = os.path.join(os.environ.get("USERPROFILE", os.path.expanduser("~")), "Desktop")
	if os.path.isdir(desktop):
		dest_addon = os.path.join(desktop, f"{addon_name}-{addon_version}.nvda-addon")
		dest_zip = os.path.join(desktop, f"{addon_name}-{addon_version}.zip")
		try:
			shutil.copyfile(output_addon, dest_addon)
			shutil.copyfile(output_zip, dest_zip)
			print(f"[Desktop] Copied both packages to Desktop: {dest_addon}")
		except Exception as e:
			print(f"[Warning] Could not copy to desktop: {e}")
	print("=" * 60)


if __name__ == "__main__":
	bundle = "--bundle-binaries" in sys.argv
	build(bundle_binaries=bundle)
